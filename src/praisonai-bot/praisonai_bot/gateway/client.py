"""
Reconnecting Gateway Client for PraisonAI.

Provides automatic reconnection with exponential backoff,
protocol version negotiation, and gap detection.
"""

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union

try:
    import websockets
    from websockets.client import WebSocketClientProtocol
except ImportError:
    raise ImportError("websockets is required. Install with: pip install websockets")

from praisonaiagents.gateway import (
    GatewayEvent,
    EventType,
    ConnectErrorCode,
    HelloResult,
    PROTOCOL_VERSION,
    MIN_PROTOCOL_VERSION,
    is_recoverable,
)

logger = logging.getLogger(__name__)

# Default capability tokens the bundled client advertises during the handshake.
DEFAULT_CAPABILITIES = ("streaming", "ack")


class PayloadTooLarge(Exception):
    """Raised when an outbound frame exceeds the server-advertised max_payload."""


class GatewayConnectError(Exception):
    """Terminal connect rejection: reconnecting will not help.

    Raised when the gateway rejects the handshake with a non-recoverable
    :class:`ConnectErrorCode` (revoked token, wrong secret, unpaired device,
    unsupported protocol, ...). The reconnect loop stops instead of hammering
    a gateway that will never accept the client, and surfaces the server's
    machine-readable recovery guidance (``code``/``next_step``) so operators
    see *why* the connection was abandoned.

    Attributes:
        code: The structured :class:`ConnectErrorCode` from the server.
        next_step: The server's recommended recovery step (``next_step`` wire
            field, e.g. ``"reauthenticate"``), if provided.
        message: Human-readable error message for display.
    """

    def __init__(
        self,
        code: ConnectErrorCode,
        next_step: Optional[str] = None,
        message: Optional[str] = None,
    ):
        self.code = code
        self.next_step = next_step
        self.message = message or ""
        super().__init__(
            f"Gateway rejected connection (code={code.value}"
            + (f", next_step={next_step}" if next_step else "")
            + (f"): {self.message}" if self.message else ")")
        )


@dataclass
class BackoffConfig:
    """Configuration for exponential backoff."""
    initial: float = 1.0  # Initial delay in seconds
    max: float = 30.0  # Maximum delay in seconds
    multiplier: float = 2.0  # Backoff multiplier
    jitter: float = 0.2  # Random jitter factor (0-1)


class ConnectionState:
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class GatewayClient:
    """Reconnecting WebSocket client for PraisonAI Gateway.
    
    Features:
    - Automatic reconnection with exponential backoff
    - Protocol version negotiation
    - Gap detection via sequence numbers
    - Cursor-based event resumption
    
    Example:
        client = GatewayClient(
            url="ws://localhost:8765",
            agent_id="my-agent",
            reconnect=True,
            backoff=BackoffConfig(initial=1, max=30)
        )
        
        # Set up gap handler
        client.on_gap = lambda expected, received: print(f"Gap detected: {expected}->{received}")
        
        # Connect and handle events
        await client.connect()
        async for event in client.events():
            print(f"Event: {event}")
    """
    
    def __init__(
        self,
        url: str,
        agent_id: str,
        token: Optional[str] = None,
        reconnect: bool = True,
        backoff: Optional[BackoffConfig] = None,
        max_reconnect_attempts: Optional[int] = None,
        capabilities: Optional[List[str]] = None,
    ):
        """Initialize the gateway client.
        
        Args:
            url: WebSocket URL to connect to
            agent_id: Agent ID to join as
            token: Optional authentication token
            reconnect: Whether to auto-reconnect on disconnect
            backoff: Backoff configuration
            max_reconnect_attempts: Max reconnection attempts (None = infinite)
            capabilities: Capability tokens to advertise during the ``hello``
                handshake (e.g. ``["streaming", "ack"]``). Defaults to
                :data:`DEFAULT_CAPABILITIES`.
        """
        self.url = url
        self.agent_id = agent_id
        self.token = token
        self.reconnect = reconnect
        self.backoff = backoff or BackoffConfig()
        self.max_reconnect_attempts = max_reconnect_attempts
        self.capabilities: List[str] = (
            list(capabilities) if capabilities is not None
            else list(DEFAULT_CAPABILITIES)
        )
        
        self._ws: Optional[WebSocketClientProtocol] = None
        self._state = ConnectionState.DISCONNECTED
        self._session_id: Optional[str] = None
        self._cursor: int = 0
        self._sequence: int = 0
        self._expected_sequence: int = 0
        self._protocol_version: int = PROTOCOL_VERSION
        self._reconnect_attempts: int = 0
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None
        # Server-supplied backoff floor (seconds) for the next reconnect delay,
        # honoured once then cleared so it does not shortcut the exponential
        # sequence on subsequent attempts.
        self._retry_after: Optional[float] = None
        
        # Negotiated handshake manifest (populated from the server's hello_ok).
        # Empty until a modern gateway is reached; a legacy gateway leaves these
        # as their permissive defaults.
        self._features: Dict[str, List[str]] = {}
        self._policy: Dict[str, int] = {}
        self._negotiated: bool = False
        
        # Callbacks
        self.on_gap: Optional[Callable[[int, int], None]] = None
        self.on_state_change: Optional[Callable[[str], None]] = None
        # Invoked when the reconnect loop stops on a terminal (non-recoverable)
        # connect failure. Receives (code, next_step) so callers can surface an
        # actionable reason and drive re-auth / re-pair instead of the client
        # silently looping forever.
        self.on_reconnect_paused: Optional[
            Callable[[ConnectErrorCode, Optional[str]], None]
        ] = None
    
    @property
    def state(self) -> str:
        """Current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Whether the client is currently connected."""
        return self._state == ConnectionState.CONNECTED
    
    @property
    def features(self) -> Dict[str, List[str]]:
        """Negotiated feature manifest (``{"methods": [...], "events": [...]}``).
        
        Empty when connected to a legacy gateway that only speaks the ``join``
        handshake. Callers should gate optional behaviour on the advertised
        event/method set rather than probing-by-failure.
        """
        return self._features
    
    @property
    def policy(self) -> Dict[str, int]:
        """Negotiated transport policy limits.
        
        Keys include ``max_payload``, ``max_buffered_bytes``,
        ``max_queued_frames`` and ``heartbeat_ms`` when advertised. Empty for a
        legacy gateway.
        """
        return self._policy
    
    @property
    def heartbeat_ms(self) -> Optional[int]:
        """Server-advertised heartbeat interval in milliseconds, if any."""
        value = self._policy.get("heartbeat_ms")
        return int(value) if value is not None else None
    
    def supports_event(self, event: Union[str, EventType]) -> bool:
        """Whether the negotiated manifest advertises the given event.
        
        Returns ``True`` for legacy gateways (no manifest) so callers keep the
        previous permissive behaviour and do not silently disable everything.
        """
        events = self._features.get("events")
        if not events:
            return True
        value = event.value if isinstance(event, EventType) else event
        return value in events
    
    def _set_state(self, state: str) -> None:
        """Set connection state and notify callback."""
        if self._state != state:
            self._state = state
            if self.on_state_change:
                self.on_state_change(state)
    
    def _calculate_backoff(self) -> float:
        """Calculate next backoff delay with jitter.

        When the server supplied a ``retry_after`` hint on the last rejection,
        it is honoured as a lower bound on the delay while preserving the
        exponential sequence: the hint delays the next attempt without
        resetting or shortcutting backoff. The hint is consumed once.
        """
        delay = min(
            self.backoff.initial * (self.backoff.multiplier ** self._reconnect_attempts),
            self.backoff.max
        )
        # Add jitter
        jitter = delay * self.backoff.jitter * (2 * random.random() - 1)
        delay = max(0, delay + jitter)

        # Honour a server-requested backoff floor once, then clear it so it
        # does not pin every subsequent attempt.
        if self._retry_after is not None:
            delay = max(delay, self._retry_after)
            self._retry_after = None

        return delay
    
    async def connect(self) -> None:
        """Start the connection loop as a background task.
        
        This method starts the reconnection loop in the background and returns
        immediately. Use events() to receive events after calling connect().
        
        Example:
            await client.connect()  # Returns immediately
            async for event in client.events():
                print(event)
        """
        if self._running:
            return
        
        self._running = True
        self._reconnect_attempts = 0
        # Discard any backoff floor left over from a previous connection loop
        # so a stale server retry_after does not pin an unrelated reconnect.
        self._retry_after = None
        self._connect_task = asyncio.create_task(self._connection_loop())
    
    async def _connection_loop(self) -> None:
        """Connection loop with automatic reconnection."""
        while self._running:
            try:
                await self._connect_once()
                
                # Reset reconnect attempts on successful connection
                self._reconnect_attempts = 0
                
                # Start receive loop
                self._receive_task = asyncio.create_task(self._receive_loop())
                
                # Wait for disconnect or stop
                await self._receive_task
                
            except GatewayConnectError as e:
                # Terminal connect rejection (auth/pairing/protocol/config):
                # the gateway will never accept this client until an operator
                # intervenes, so stop the loop instead of hammering it forever.
                logger.error(
                    f"Connection abandoned: {e} "
                    f"(reconnect paused; not retrying)"
                )
                self._running = False
                self._set_state(ConnectionState.DISCONNECTED)
                if self.on_reconnect_paused:
                    self.on_reconnect_paused(e.code, e.next_step)
                return
            except ValueError as e:
                # Protocol version mismatch is a permanent error
                logger.error(f"Connection failed permanently: {e}")
                self._running = False
                raise
            except Exception as e:
                logger.error(f"Connection error: {e}")
            
            if not self._running or not self.reconnect:
                break
            
            # Check max attempts
            if self.max_reconnect_attempts and self._reconnect_attempts >= self.max_reconnect_attempts:
                logger.error(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached")
                break
            
            # Calculate backoff delay
            self._reconnect_attempts += 1
            delay = self._calculate_backoff()
            
            logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})")
            self._set_state(ConnectionState.RECONNECTING)
            
            await asyncio.sleep(delay)
    
    async def _connect_once(self) -> None:
        """Establish WebSocket connection and perform handshake."""
        self._set_state(ConnectionState.CONNECTING)
        
        # Build connection URL with token if provided
        connect_url = self.url
        if self.token:
            separator = "&" if "?" in connect_url else "?"
            connect_url = f"{connect_url}{separator}token={self.token}"
        
        # Connect to WebSocket
        self._ws = await websockets.connect(connect_url)
        
        # Resume fields shared by both handshake paths.
        resume_fields: Dict[str, Any] = {}
        if self._session_id:
            resume_fields["session_id"] = self._session_id
        if self._cursor > 0:
            resume_fields["since"] = self._cursor
        
        # Modern path: send the capability-aware hello frame and let the
        # gateway advertise its features/policy so we can self-configure.
        hello_msg = {
            "type": "hello",
            "agent_id": self.agent_id,
            "protocol_min": MIN_PROTOCOL_VERSION,
            "protocol_max": PROTOCOL_VERSION,
            "capabilities": list(self.capabilities),
            **resume_fields,
        }
        await self._ws.send(json.dumps(hello_msg))
        
        # Wait for handshake response with timeout
        try:
            response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        except asyncio.TimeoutError:
            raise ConnectionError("Handshake timed out")
        data = json.loads(response)
        reply_type = data.get("type")
        
        if reply_type == "hello_ok":
            self._adopt_hello(data)
        
        elif reply_type == "hello_error":
            error_code = data.get("code")
            error_msg = data.get("message", "Unknown error")
            if error_code in ("protocol_unsupported", "version_unsupported"):
                raise ValueError(f"Protocol version unsupported: {error_msg}")
            raise ConnectionError(f"Handshake failed: {error_msg}")
        
        elif reply_type == "error":
            error_code = data.get("code")
            error_msg = data.get("message", "Unknown error")
            if error_code == "version_unsupported":
                raise ValueError(f"Protocol version unsupported: {error_msg}")
            # A bare "error" reply to hello means an older gateway that does not
            # speak the hello frame; fall back to the legacy join handshake.
            await self._legacy_join(resume_fields)
        
        elif reply_type == "joined":
            # Older gateway answered the hello frame with a bare joined reply.
            self._adopt_legacy_join(data)
        
        else:
            raise ConnectionError(f"Unexpected handshake reply: {reply_type}")
    
    def _adopt_hello(self, data: Dict[str, Any]) -> None:
        """Adopt a negotiated ``hello_ok`` manifest (features + policy)."""
        hello = HelloResult(
            protocol=data.get("protocol", PROTOCOL_VERSION),
            features=data.get("features", {}) or {},
            policy=data.get("policy", {}) or {},
            session_id=data.get("session_id"),
            resumed=data.get("resumed", False),
            cursor=data.get("cursor", 0),
        )
        self._session_id = hello.session_id
        self._cursor = hello.cursor
        self._sequence = data.get("sequence", 0)
        self._expected_sequence = self._sequence + 1
        self._protocol_version = hello.protocol
        self._features = hello.features
        self._policy = hello.policy
        self._negotiated = True
        
        self._set_state(ConnectionState.CONNECTED)
        logger.info(
            f"Connected to gateway (session={self._session_id}, "
            f"protocol=v{self._protocol_version}, resumed={hello.resumed}, "
            f"features={self._features}, policy={self._policy})"
        )
    
    async def _legacy_join(self, resume_fields: Dict[str, Any]) -> None:
        """Compatibility fallback: perform the legacy ``join`` handshake."""
        logger.info("Gateway did not accept hello; falling back to legacy join")
        join_msg = {
            "type": "join",
            "agent_id": self.agent_id,
            "min_version": MIN_PROTOCOL_VERSION,
            "max_version": PROTOCOL_VERSION,
            **resume_fields,
        }
        await self._ws.send(json.dumps(join_msg))
        
        try:
            response = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
        except asyncio.TimeoutError:
            raise ConnectionError("Join handshake timed out")
        data = json.loads(response)
        
        if data.get("type") in ("error", "hello_error"):
            error_code = data.get("code")
            error_msg = data.get("message", "Unknown error")
            next_step = data.get("next_step") or data.get("next")

            # Record a server-supplied backoff floor for the next reconnect,
            # regardless of terminal/transient (a terminal path ignores it).
            retry_after = data.get("retry_after_seconds")
            if retry_after is not None:
                try:
                    self._retry_after = max(0.0, float(retry_after))
                except (TypeError, ValueError):
                    self._retry_after = None

            # Legacy string codes kept for backward compatibility.
            if error_code in ("version_unsupported", "protocol_unsupported"):
                raise ValueError(f"Protocol version unsupported: {error_msg}")

            # Structured connect-error code: branch terminal vs transient using
            # the shared core classifier so a revoked token / wrong secret /
            # unpaired device stops the loop with an actionable reason instead
            # of reconnecting forever.
            if error_code is not None:
                try:
                    code = ConnectErrorCode(error_code)
                except ValueError:
                    # Unknown/future code: treat as transient (retry).
                    raise ConnectionError(f"Join failed: {error_msg}")

                if not is_recoverable(code):
                    raise GatewayConnectError(code, next_step, error_msg)

                # Recoverable → let the loop back off and retry (honouring any
                # retry_after floor recorded above).
                raise ConnectionError(f"Join failed: {error_msg}")

            # No structured code at all: transient by default.
            raise ConnectionError(f"Join failed: {error_msg}")
        
        elif data.get("type") == "joined":
            self._adopt_legacy_join(data)
        else:
            raise ConnectionError(f"Unexpected join reply: {data.get('type')}")
    
    def _adopt_legacy_join(self, data: Dict[str, Any]) -> None:
        """Adopt a bare legacy ``joined`` reply (no features/policy manifest)."""
        self._session_id = data.get("session_id")
        self._cursor = data.get("cursor", 0)
        self._sequence = data.get("sequence", 0)
        self._expected_sequence = self._sequence + 1
        self._protocol_version = data.get("protocol_version", PROTOCOL_VERSION)
        # Legacy gateway advertises no manifest; keep permissive defaults.
        self._features = {}
        self._policy = {}
        self._negotiated = False
        
        self._set_state(ConnectionState.CONNECTED)
        logger.info(
            f"Connected to gateway via legacy join (session={self._session_id}, "
            f"protocol=v{self._protocol_version}, resumed={data.get('resumed', False)})"
        )
    
    async def _receive_loop(self) -> None:
        """Receive messages from WebSocket."""
        try:
            while self._ws and not self._ws.closed:
                message = await self._ws.recv()
                data = json.loads(message)
                
                # Handle different message types
                msg_type = data.get("type")
                
                if msg_type == "replay":
                    # Handle replayed event
                    event_data = data.get("event", {})
                    event = GatewayEvent.from_dict(event_data)
                    await self._handle_event(event)
                
                elif msg_type == "event":
                    # Handle regular event
                    event = GatewayEvent.from_dict(data)
                    await self._handle_event(event)
                
                else:
                    # Queue other messages as events
                    event = GatewayEvent(
                        type=msg_type or "message",
                        data=data
                    )
                    await self._event_queue.put(event)
                
        except websockets.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
        finally:
            self._set_state(ConnectionState.DISCONNECTED)
    
    async def _handle_event(self, event: GatewayEvent) -> None:
        """Handle an event with gap detection."""
        # Check for sequence gap
        if event.sequence is not None:
            if event.sequence != self._expected_sequence:
                # Gap detected
                gap_size = event.sequence - self._expected_sequence
                logger.warning(
                    f"Gap detected: expected seq {self._expected_sequence}, "
                    f"received {event.sequence} (missed {gap_size} events)"
                )
                
                if self.on_gap:
                    self.on_gap(self._expected_sequence, event.sequence)
            
            self._expected_sequence = event.sequence + 1
        
        # Update cursor if present
        cursor = event.data.get("cursor")
        if cursor is not None:
            self._cursor = cursor
        
        # Queue the event
        await self._event_queue.put(event)
    
    async def disconnect(self) -> None:
        """Disconnect from the gateway."""
        self._running = False
        
        # Cancel connect task if running
        if hasattr(self, '_connect_task') and self._connect_task:
            self._connect_task.cancel()
            try:
                await self._connect_task
            except asyncio.CancelledError:
                pass
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        self._set_state(ConnectionState.DISCONNECTED)
    
    async def send(self, message: Union[str, Dict[str, Any]]) -> None:
        """Send a message to the gateway.
        
        Args:
            message: Message content (string or dict)
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to gateway")
        
        if isinstance(message, dict):
            payload = json.dumps(message)
        else:
            payload = json.dumps({
                "type": "message",
                "content": message
            })
        
        # Self-guard against the server-advertised max_payload so oversized
        # frames fail locally with a clear error instead of being rejected
        # (or silently dropped) by the gateway.
        max_payload = self._policy.get("max_payload")
        if max_payload and len(payload.encode("utf-8")) > max_payload:
            raise PayloadTooLarge(
                f"Outbound frame exceeds server max_payload "
                f"({len(payload.encode('utf-8'))} > {max_payload} bytes)"
            )
        
        await self._ws.send(payload)
    
    async def events(self) -> AsyncIterator[GatewayEvent]:
        """Iterate over received events.
        
        Yields:
            Gateway events as they are received
        """
        while self._running:
            try:
                # Use timeout to periodically check if still running
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                yield event
            except asyncio.TimeoutError:
                continue
    
    async def resync(self) -> None:
        """Force a full resynchronization.
        
        Useful when a gap is detected beyond the replay window.
        """
        logger.info("Forcing resynchronization")
        
        # Reset cursor to trigger full resync
        self._cursor = 0
        self._sequence = 0
        self._expected_sequence = 0
        
        # Disconnect and reconnect
        if self._ws:
            await self._ws.close()


async def example_usage():
    """Example usage of the GatewayClient."""
    client = GatewayClient(
        url="ws://localhost:8765",
        agent_id="example-agent",
        reconnect=True,
        backoff=BackoffConfig(initial=1, max=30, jitter=0.2)
    )
    
    # Set up event handlers
    def on_gap(expected: int, received: int):
        print(f"Gap detected: expected {expected}, got {received}")
        # Could trigger resync here if gap is too large
    
    def on_state_change(state: str):
        print(f"Connection state: {state}")
    
    client.on_gap = on_gap
    client.on_state_change = on_state_change
    
    try:
        # Start connection (returns immediately)
        await client.connect()
        
        # Process events
        async for event in client.events():
            print(f"Event: {event.type}, Data: {event.data}")
            
            # Send a response
            if event.type == EventType.MESSAGE:
                await client.send("Got your message!")
    
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(example_usage())