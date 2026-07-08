"""
Gateway Protocols for PraisonAI Agents.

Defines the interfaces for gateway/control plane implementations.
These protocols enable multi-agent coordination, session management,
and real-time communication.

All implementations live in the ``praisonai-bot`` package (``praisonai_bot.gateway``).
The ``praisonai`` wrapper provides backward-compatible shims.
"""

from __future__ import annotations

import time
import uuid
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    Iterator,
    List,
    Literal,
    Optional,
    Protocol,
    Set,
    Tuple,
    TypedDict,
    Union,
    runtime_checkable,
)

# Gateway protocol versioning constants
GATEWAY_PROTOCOL_VERSION = 1
MIN_CLIENT_PROTOCOL_VERSION = 1

if TYPE_CHECKING:
    from praisonai.gateway.pairing import PairedChannel
    from ..agent import Agent
    from ..bots.presentation import MessagePresentation
    from ..scheduler.models import DeliveryTarget


class ConnectErrorCode(str, Enum):
    """Structured error codes for connection failures."""
    AUTH_REQUIRED = "auth_required"
    AUTH_UNAUTHORIZED = "auth_unauthorized"
    PROTOCOL_UNSUPPORTED = "protocol_unsupported"
    PAIRING_REQUIRED = "pairing_required"
    AGENT_NOT_FOUND = "agent_not_found"
    RATE_LIMITED = "rate_limited"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"
    CONFIGURATION_ERROR = "configuration_error"


class GatewayCloseCode(str, Enum):
    """Structured, machine-readable reasons for a server-initiated close.

    Distinct from :class:`ConnectErrorCode` (which describes why a *connection*
    was rejected at/handshake time), these describe why an already-established
    connection is being torn down by the server mid-session.

    Codes:
        SLOW_CONSUMER: The client's outbound buffer exceeded the gateway's
            advertised ``max_buffered_bytes`` policy (a genuinely slow/stalled
            consumer). The server evicts it so its backlog cannot grow without
            bound or stall delivery to healthy clients.
        CREDENTIALS_ROTATED: The shared gateway secret this session
            authenticated under is no longer the active secret (an operator
            rotated ``auth_token`` and hot-reloaded, or otherwise revoked it).
            The server force-closes every session stamped with a stale secret
            so a leaked/revoked credential stops working within one reload
            cycle, without a full process restart. Clients should
            re-authenticate (see :attr:`ConnectRecoveryStep.REAUTHENTICATE`)
            and reconnect with fresh credentials rather than backing off as if
            the server were down.
        LIVENESS_TIMEOUT: The connection missed too many application-level
            heartbeats (see :class:`LivenessPolicy`): its ``last_activity``
            exceeded ``interval_ms × missed_beats_before_reap``, so the server
            treats it as a dead/half-open peer and reaps it, releasing the
            session/presence/queue state deterministically. Half-open sockets
            behind NAT/proxies/mobile networks — where the peer has vanished
            but no FIN/RST ever arrives — are the motivating case. Clients
            should reconnect (their own watchdog typically force-reconnects
            first) rather than treating this as a fatal error.
    """

    SLOW_CONSUMER = "slow_consumer"
    CREDENTIALS_ROTATED = "credentials_rotated"
    LIVENESS_TIMEOUT = "liveness_timeout"


class ConnectRecoveryStep(str, Enum):
    """Machine-readable recovery hint for a connection rejection.

    Clients branch on ``(code, next_step)`` to implement deterministic,
    uniform reconnect behaviour without parsing free-text reasons:

        REAUTHENTICATE: Obtain fresh credentials, then reconnect.
        REPAIR:         Re-run the device pairing flow, then reconnect.
        UPGRADE_CLIENT: The client protocol is too old; update the client.
        DOWNGRADE_CLIENT: The client protocol is newer than the server
            supports; use an older client or wait for a server upgrade.
        WAIT_THEN_RETRY: Back off (see ``retry_after_seconds``) then reconnect.
        DO_NOT_RETRY:   The rejection is terminal; reconnecting will not help.
    """

    REAUTHENTICATE = "reauthenticate"
    REPAIR = "repair"
    UPGRADE_CLIENT = "upgrade_client"
    DOWNGRADE_CLIENT = "downgrade_client"
    WAIT_THEN_RETRY = "wait_then_retry"
    DO_NOT_RETRY = "do_not_retry"


class EventType(str, Enum):
    """Standard gateway event types."""
    
    # Connection events
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"
    
    # Session events
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SESSION_UPDATE = "session_update"
    
    # Agent events
    AGENT_REGISTER = "agent_register"
    AGENT_UNREGISTER = "agent_unregister"
    AGENT_STATUS = "agent_status"
    
    # Message events
    MESSAGE = "message"
    MESSAGE_ACK = "message_ack"
    MESSAGE_ABORT = "message_abort"
    TYPING = "typing"
    
    # Streaming events (relayed from agent's StreamEventEmitter)
    TOKEN_STREAM = "token_stream"
    TOOL_CALL_STREAM = "tool_call_stream"
    STREAM_END = "stream_end"
    
    # System events
    HEALTH = "health"
    ERROR = "error"
    BROADCAST = "broadcast"

    # Liveness events (application-level heartbeat, transport-agnostic)
    PING = "ping"
    PONG = "pong"
    
    # Push channel events
    CHANNEL_SUBSCRIBE = "channel_subscribe"
    CHANNEL_UNSUBSCRIBE = "channel_unsubscribe"
    CHANNEL_MESSAGE = "channel_message"
    CHANNEL_CREATED = "channel_created"
    CHANNEL_DELETED = "channel_deleted"
    
    # Presence events
    PRESENCE_JOIN = "presence_join"
    PRESENCE_LEAVE = "presence_leave"
    PRESENCE_UPDATE = "presence_update"
    
    # Delivery events
    MESSAGE_NACK = "message_nack"
    DELIVERY_RETRY = "delivery_retry"
    
    # Polling events
    POLL_REQUEST = "poll_request"
    POLL_RESPONSE = "poll_response"
    
    # Handshake events
    HELLO = "hello"
    HELLO_OK = "hello_ok"
    HELLO_ERROR = "hello_error"


class OperatorScope(str, Enum):
    """Operator authorisation scopes for multi-operator Gateway access control.

    These describe *what an authenticated operator is allowed to do*, layered on
    top of (and orthogonal to) authentication. The vocabulary lives in the core
    SDK so that protocol clients and the wrapper Gateway share the same names;
    enforcement happens in the wrapper where requests are dispatched.

    Scopes:
        READ:      View dashboard / receive session transcripts and status.
        WRITE:     Send messages as the agent.
        APPROVALS: Resolve tool-execution approvals (security-sensitive).
        PAIRING:   Approve / revoke device pairing.
        ADMIN:     Channel control (pause / resume / reconnect) and management.
    """

    READ = "read"
    WRITE = "write"
    APPROVALS = "approvals"
    PAIRING = "pairing"
    ADMIN = "admin"

    @classmethod
    def all(cls) -> "List[OperatorScope]":
        """Return every scope (granted by default when no policy is configured)."""
        return list(cls)


@dataclass
class HelloParams:
    """Parameters for initiating a versioned handshake.
    
    Attributes:
        agent_id: The agent to connect to
        protocol_min: Minimum protocol version the client supports
        protocol_max: Maximum protocol version the client supports
        capabilities: Optional list of capability tokens the client supports
        session_id: Optional session to resume
        since: Optional cursor for event replay
    """
    agent_id: str
    protocol_min: int
    protocol_max: int
    capabilities: List[str] = field(default_factory=list)
    session_id: Optional[str] = None
    since: Optional[int] = None


@dataclass
class HelloResult:
    """Result of a successful handshake negotiation.
    
    Attributes:
        protocol: The negotiated protocol version
        features: Supported methods and events
        policy: Gateway policy limits (max_payload, heartbeat_ms, etc.)
        session_id: The session ID for this connection
        resumed: Whether an existing session was resumed
        cursor: Current event cursor position
    """
    protocol: int
    features: Dict[str, List[str]]  # {"methods": [...], "events": [...]}
    policy: Dict[str, int]  # {"max_payload": ..., "heartbeat_ms": ...}
    session_id: str
    resumed: bool
    cursor: int


@dataclass
class HelloError:
    """Structured connect-rejection envelope.

    Emitted from *every* connection rejection path — both pre-handshake
    transport checks (auth/origin/rate-limit) and handshake negotiation —
    so clients can implement deterministic reconnect logic by branching on
    ``(code, next_step)`` instead of string-matching close reasons.

    Attributes:
        code: Structured, machine-readable error code.
        message: Human-readable error message (display only).
        next_step: Machine-readable recovery hint telling the client what to
            do next (re-authenticate, re-pair, upgrade, wait then retry, ...).
        retry_after_seconds: Optional backoff hint (rate limiting / transient
            unavailability). Only meaningful with ``WAIT_THEN_RETRY``.
        next_action: Deprecated free-text hint, retained for backward
            compatibility. Prefer ``next_step``.
    """
    code: ConnectErrorCode
    message: str
    next_step: Optional[ConnectRecoveryStep] = None
    retry_after_seconds: Optional[int] = None
    next_action: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a ``hello_error`` wire frame.

        The ``next`` key is preserved for backward compatibility with existing
        clients; ``next_step`` and ``retry_after_seconds`` are the structured
        recovery fields new clients should branch on.
        """
        frame: Dict[str, Any] = {
            "type": "hello_error",
            "code": self.code.value,
            "message": self.message,
        }
        if self.next_step is not None:
            frame["next_step"] = self.next_step.value
        if self.retry_after_seconds is not None:
            frame["retry_after_seconds"] = self.retry_after_seconds
        # Backward-compatible legacy field: fall back to next_step's value.
        # Omitted entirely when there is no recovery hint so clients using
        # strict schema validation or ``if frame["next"]`` are not tripped by
        # an explicit ``null``.
        legacy_next = self.next_action
        if legacy_next is None and self.next_step is not None:
            legacy_next = self.next_step.value
        if legacy_next is not None:
            frame["next"] = legacy_next
        return frame


@dataclass
class GatewayEvent:
    """A gateway event with metadata.
    
    Attributes:
        type: The event type
        data: Event payload
        event_id: Unique event identifier
        timestamp: Event creation time
        source: Source identifier (agent_id, client_id, etc.)
        target: Target identifier (optional, for directed events)
        sequence: Monotonic sequence number for gap detection (optional)
    
    Wire Protocol Extensions:
        When events are sent over the gateway, additional fields are added:
        - seq: Top-level monotonic sequence number for gap detection
        - cursor: Event cursor position (also stored in data['cursor'])
        
    Resume Protocol:
        The 'joined' acknowledgment includes:
        - cursor: Current head cursor position
        - oldest_cursor: Oldest event still in buffer
        - resync_required: True if requested 'since' is below oldest_cursor
        
        When resync_required=true, a 'snapshot' message follows with full state.
    """
    
    type: Union[EventType, str]
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    target: Optional[str] = None
    sequence: Optional[int] = None  # Monotonic sequence for gap detection
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "data": self.data,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "target": self.target,
        }
        if self.sequence is not None:
            result["sequence"] = self.sequence
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayEvent":
        """Create from dictionary."""
        event_type = data.get("type", "message")
        try:
            event_type = EventType(event_type)
        except ValueError:
            pass  # Keep as string for custom event types
        
        return cls(
            type=event_type,
            data=data.get("data", {}),
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            source=data.get("source"),
            target=data.get("target"),
            sequence=data.get("sequence"),
        )


@dataclass
class GatewayMessage:
    """A message sent through the gateway.
    
    Attributes:
        content: Message content (text or structured data)
        sender_id: Sender identifier
        session_id: Session this message belongs to
        message_id: Unique message identifier
        timestamp: Message creation time
        metadata: Additional message metadata
        reply_to: ID of message being replied to (optional)
        presentation: Optional interactive presentation (buttons, menus, etc.)
    """
    
    content: Union[str, Dict[str, Any]]
    sender_id: str
    session_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None
    presentation: Optional["MessagePresentation"] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {
            "content": self.content,
            "sender_id": self.sender_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "reply_to": self.reply_to,
        }
        if self.presentation is not None:
            data["presentation"] = self.presentation.to_dict()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayMessage":
        """Create from dictionary."""
        from ..bots.presentation import MessagePresentation
        
        presentation = None
        raw_presentation = data.get("presentation")
        if isinstance(raw_presentation, dict):
            presentation = MessagePresentation.from_dict(raw_presentation)
        
        return cls(
            content=data.get("content", ""),
            sender_id=data.get("sender_id", "unknown"),
            session_id=data.get("session_id", "default"),
            message_id=data.get("message_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            reply_to=data.get("reply_to"),
            presentation=presentation,
        )


@runtime_checkable
class GatewaySessionProtocol(Protocol):
    """Protocol for gateway session management.
    
    Sessions track conversations between clients and agents,
    maintaining state and message history.
    """
    
    @property
    def session_id(self) -> str:
        """Unique session identifier."""
        ...
    
    @property
    def agent_id(self) -> Optional[str]:
        """ID of the agent handling this session."""
        ...
    
    @property
    def client_id(self) -> Optional[str]:
        """ID of the client in this session."""
        ...
    
    @property
    def is_active(self) -> bool:
        """Whether the session is currently active."""
        ...
    
    @property
    def created_at(self) -> float:
        """Session creation timestamp."""
        ...
    
    @property
    def last_activity(self) -> float:
        """Last activity timestamp."""
        ...
    
    def get_state(self) -> Dict[str, Any]:
        """Get session state."""
        ...
    
    def set_state(self, key: str, value: Any) -> None:
        """Set a session state value."""
        ...
    
    def add_message(self, message: GatewayMessage) -> None:
        """Add a message to the session history."""
        ...
    
    def get_messages(self, limit: Optional[int] = None) -> List[GatewayMessage]:
        """Get session message history."""
        ...
    
    def close(self) -> None:
        """Close the session."""
        ...


@runtime_checkable
class GatewayClientProtocol(Protocol):
    """Protocol for gateway client connections.
    
    Clients are external connections (WebSocket, HTTP, etc.)
    that communicate with agents through the gateway.
    """
    
    @property
    def client_id(self) -> str:
        """Unique client identifier."""
        ...
    
    @property
    def is_connected(self) -> bool:
        """Whether the client is currently connected."""
        ...
    
    @property
    def connected_at(self) -> float:
        """Connection timestamp."""
        ...
    
    async def send(self, event: GatewayEvent) -> None:
        """Send an event to the client."""
        ...
    
    async def receive(self) -> GatewayEvent:
        """Receive an event from the client."""
        ...
    
    async def close(self) -> None:
        """Close the client connection."""
        ...


@runtime_checkable
class GatewayProtocol(Protocol):
    """Protocol for gateway/control plane implementations.
    
    The gateway coordinates communication between clients and agents,
    manages sessions, and provides health/presence tracking.
    
    Example usage (implementation in praisonai_bot.gateway):
        from praisonai.gateway import WebSocketGateway
        
        gateway = WebSocketGateway(port=8765)
        gateway.register_agent(my_agent)
        await gateway.start()
    """
    
    @property
    def is_running(self) -> bool:
        """Whether the gateway is currently running."""
        ...
    
    @property
    def port(self) -> int:
        """Port the gateway is listening on."""
        ...
    
    @property
    def host(self) -> str:
        """Host the gateway is bound to."""
        ...
    
    # Lifecycle methods
    async def start(self) -> None:
        """Start the gateway server."""
        ...
    
    async def stop(self) -> None:
        """Stop the gateway server."""
        ...
    
    # Agent management
    def register_agent(self, agent: "Agent", agent_id: Optional[str] = None) -> str:
        """Register an agent with the gateway.
        
        Args:
            agent: The agent to register
            agent_id: Optional custom agent ID
            
        Returns:
            The agent ID (generated if not provided)
        """
        ...
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the gateway.
        
        Args:
            agent_id: The agent ID to unregister
            
        Returns:
            True if agent was unregistered, False if not found
        """
        ...
    
    def get_agent(self, agent_id: str) -> Optional["Agent"]:
        """Get a registered agent by ID."""
        ...
    
    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        ...
    
    # Session management
    def create_session(
        self,
        agent_id: str,
        client_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GatewaySessionProtocol:
        """Create a new session.
        
        Args:
            agent_id: The agent to handle this session
            client_id: Optional client ID
            session_id: Optional custom session ID
            
        Returns:
            The created session
        """
        ...
    
    def get_session(self, session_id: str) -> Optional[GatewaySessionProtocol]:
        """Get a session by ID."""
        ...
    
    def close_session(self, session_id: str) -> bool:
        """Close a session.
        
        Args:
            session_id: The session ID to close
            
        Returns:
            True if session was closed, False if not found
        """
        ...
    
    def list_sessions(self, agent_id: Optional[str] = None) -> List[str]:
        """List session IDs, optionally filtered by agent."""
        ...
    
    # Event handling
    def on_event(self, event_type: Union[EventType, str]) -> Callable:
        """Decorator to register an event handler.
        
        Example:
            @gateway.on_event(EventType.MESSAGE)
            async def handle_message(event: GatewayEvent):
                print(f"Message: {event.data}")
        """
        ...
    
    async def emit(self, event: GatewayEvent) -> None:
        """Emit an event to registered handlers."""
        ...
    
    async def broadcast(
        self,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Broadcast an event to all connected clients.
        
        Args:
            event: The event to broadcast
            exclude: Optional list of client IDs to exclude
        """
        ...
    
    # Health and status
    def health(self) -> Dict[str, Any]:
        """Get gateway health status.
        
        Returns:
            Health information including:
            - status: "healthy" or "unhealthy"
            - uptime: Seconds since start
            - agents: Number of registered agents
            - sessions: Number of active sessions
            - clients: Number of connected clients
        """
        ...


# ---------------------------------------------------------------------------
# Push notification dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ChannelInfo:
    """Metadata about a push channel/topic.
    
    Attributes:
        name: Channel name (unique identifier)
        created_at: Channel creation timestamp
        metadata: Arbitrary channel metadata
        subscriber_count: Current number of subscribers
    """
    
    name: str
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    subscriber_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "subscriber_count": self.subscriber_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChannelInfo":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            created_at=data.get("created_at", time.time()),
            metadata=data.get("metadata", {}),
            subscriber_count=data.get("subscriber_count", 0),
        )


@dataclass
class PresenceInfo:
    """Presence information for a connected client.
    
    Attributes:
        client_id: Client identifier
        status: Presence status ("online", "idle", "offline")
        last_seen: Last heartbeat timestamp
        metadata: Client-provided metadata (e.g., display name)
        channels: Channels this client is subscribed to
    """
    
    client_id: str
    status: str = "online"
    last_seen: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    channels: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "client_id": self.client_id,
            "status": self.status,
            "last_seen": self.last_seen,
            "metadata": self.metadata,
            "channels": self.channels,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresenceInfo":
        """Create from dictionary."""
        return cls(
            client_id=data.get("client_id", ""),
            status=data.get("status", "online"),
            last_seen=data.get("last_seen", time.time()),
            metadata=data.get("metadata", {}),
            channels=data.get("channels", []),
        )


# ---------------------------------------------------------------------------
# Push notification protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class PushChannelProtocol(Protocol):
    """Protocol for channel/topic-based push messaging.
    
    Channels group clients by interest. Messages published to a channel
    are delivered to all subscribed clients.
    """
    
    def add_channel(
        self, channel_name: str, metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a named channel.
        
        Args:
            channel_name: Unique channel name
            metadata: Optional channel metadata
            
        Returns:
            True if created, False if already exists
        """
        ...
    
    def remove_channel(self, channel_name: str) -> bool:
        """Delete a channel and unsubscribe all clients.
        
        Returns:
            True if removed, False if not found
        """
        ...
    
    def get_channel(self, channel_name: str) -> Optional[ChannelInfo]:
        """Get channel metadata."""
        ...
    
    def list_channels(self) -> List[str]:
        """List all active channel names."""
        ...
    
    def subscribe_client(self, client_id: str, channel_name: str) -> bool:
        """Subscribe a client to a channel.
        
        Returns:
            True if subscribed, False if already subscribed or channel missing
        """
        ...
    
    def unsubscribe_client(self, client_id: str, channel_name: str) -> bool:
        """Unsubscribe a client from a channel.
        
        Returns:
            True if unsubscribed, False if not subscribed
        """
        ...
    
    def get_subscribers(self, channel_name: str) -> List[str]:
        """List client IDs subscribed to a channel."""
        ...
    
    def get_client_channels(self, client_id: str) -> List[str]:
        """List channels a client is subscribed to."""
        ...
    
    async def publish_to_channel(
        self,
        channel_name: str,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> int:
        """Publish an event to all subscribers of a channel.
        
        Args:
            channel_name: Target channel
            event: The event to deliver
            exclude: Optional client IDs to skip
            
        Returns:
            Number of clients the event was sent to
        """
        ...


@runtime_checkable
class PresenceProtocol(Protocol):
    """Protocol for tracking client presence (online/idle/offline)."""
    
    async def track_presence(
        self,
        client_id: str,
        status: str = "online",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Set or update a client's presence status.
        
        Args:
            client_id: Client identifier
            status: Presence status ("online", "idle", "offline")
            metadata: Optional client metadata
        """
        ...
    
    async def remove_presence(self, client_id: str) -> None:
        """Remove a client's presence (on disconnect)."""
        ...
    
    def get_presence(self, client_id: str) -> Optional[PresenceInfo]:
        """Get a single client's presence info."""
        ...
    
    def get_all_presence(
        self, channel_name: Optional[str] = None,
    ) -> List[PresenceInfo]:
        """Get presence info, optionally filtered by channel.
        
        Args:
            channel_name: If provided, only return presence for channel members
        """
        ...
    
    def get_online_count(self, channel_name: Optional[str] = None) -> int:
        """Count online clients, optionally filtered by channel."""
        ...


@runtime_checkable
class DeliveryGuaranteeProtocol(Protocol):
    """Protocol for at-least-once message delivery.
    
    Messages are stored, tracked, and retried until acknowledged.
    """
    
    async def store_message(self, event: GatewayEvent) -> str:
        """Persist a message to the store.
        
        Returns:
            The event_id of the stored message
        """
        ...
    
    async def acknowledge(self, client_id: str, event_id: str) -> bool:
        """Mark a message as acknowledged by a client.
        
        Returns:
            True if found and acknowledged, False if not found
        """
        ...
    
    async def nack(self, client_id: str, event_id: str) -> None:
        """Negative acknowledge - request redelivery."""
        ...
    
    async def get_unacknowledged(
        self, client_id: str, limit: int = 100,
    ) -> List[GatewayEvent]:
        """Get pending unacknowledged messages for a client."""
        ...
    
    async def retry_unacknowledged(self, client_id: str) -> int:
        """Redeliver all unacknowledged messages to a client.
        
        Returns:
            Number of messages redelivered
        """
        ...
    
    async def purge_acknowledged(self, max_age_seconds: int = 86400) -> int:
        """Remove old acknowledged messages from the store.
        
        Returns:
            Number of messages purged
        """
        ...


@runtime_checkable
class OutboundDeliveryProtocol(Protocol):
    """Protocol for durable outbound message delivery.
    
    Ensures messages sent to external channels (Telegram, Slack, Discord, etc.)
    are persisted before sending and can be retried on failure. This provides
    crash-safe at-least-once delivery for channel replies.
    
    Example usage (implementation in praisonai_bot.gateway):
        from praisonai.bots import OutboundQueue
        
        outbox = OutboundQueue(path="~/.praisonai/state/outbox.sqlite")
        
        # Enqueue before sending
        key = await outbox.enqueue(
            idempotency_key="msg-123",
            target_channel="telegram:12345",
            payload={"text": "Hello", "metadata": {...}}
        )
        
        # Attempt delivery
        success = await deliver_with_retry(adapter, channel_id, payload)
        
        # Mark as sent only if successful
        if success:
            await outbox.mark_sent(key)
        
        # On restart, drain pending messages
        await outbox.drain(delivery_handler)
    """
    
    async def enqueue(
        self,
        idempotency_key: str,
        target: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist an outbound message for delivery.
        
        Args:
            idempotency_key: Unique key to prevent duplicate sends
            target: Target channel identifier (e.g., "telegram:12345")
            payload: Message payload to deliver
            metadata: Optional metadata for tracking/routing
            
        Returns:
            Unique entry key for tracking this message
        """
        ...
    
    async def mark_sent(self, key: str) -> bool:
        """Mark a message as successfully sent.
        
        Args:
            key: The entry key returned by enqueue()
            
        Returns:
            True if marked successfully, False if not found
        """
        ...
    
    async def mark_failed(
        self,
        key: str,
        error: str,
        permanent: bool = False,
    ) -> bool:
        """Mark a message as failed.
        
        Args:
            key: The entry key returned by enqueue()
            error: Error description
            permanent: If True, won't retry this message
            
        Returns:
            True if marked successfully, False if not found
        """
        ...
    
    async def drain(
        self,
        sender: Callable[[str, Dict[str, Any]], Awaitable[bool]],
        limit: Optional[int] = None,
    ) -> tuple[int, int]:
        """Process pending messages.
        
        Called on startup to retry unsent messages. Messages are processed
        oldest-first to maintain order.
        
        Args:
            sender: Async function that attempts delivery. Should return
                    True on success, False to retry later.
            limit: Optional max messages to process
            
        Returns:
            Tuple of (succeeded, failed) counts
        """
        ...
    
    def pending_count(self) -> int:
        """Get count of pending messages awaiting delivery."""
        ...
    
    def size(self) -> int:
        """Get total number of messages in queue."""
        ...
    
    async def purge_old(self, max_age_seconds: int = 86400 * 7) -> int:
        """Remove old sent messages.
        
        Args:
            max_age_seconds: Age threshold for removal
            
        Returns:
            Number of messages purged
        """
        ...


# ---------------------------------------------------------------------------
# Per-route, trust-tiered toolset scoping (Issue #2298)
# ---------------------------------------------------------------------------

# Conservative deny-list applied to ``trust: "untrusted"`` routes.  Inbound
# content from strangers / generic webhooks is the framework's largest
# prompt-injection surface, so dangerous tool *families* are never advertised
# to the model on these routes (shell, file mutation, delegation,
# self-scheduling).  Names are matched case-insensitively against substrings of
# the tool name so deployments do not have to enumerate every concrete tool.
UNTRUSTED_DENY_SUBSTRINGS: List[str] = [
    "shell",
    "exec",
    "command",
    "subprocess",
    "write_file",
    "edit_file",
    "delete_file",
    "rm_file",
    "delegate",
    "handoff",
    "cronjob",
    "schedule",
]

# Trust tiers, ordered from least to most privileged.
TRUST_TIERS: List[str] = ["untrusted", "standard", "trusted"]


@dataclass
class ToolPolicy:
    """Declarative, per-route scope applied to an agent's tool surface.

    Mirrors the scheduler's ``RunPolicy.filter_tools`` contract (wrapper layer)
    but lives in core so :class:`RouteBinding` can *declare* the scope without
    importing any heavy wrapper code.  The wrapper inbound path applies it via a
    small apply/restore helper, exactly as the scheduler already does for
    unattended runs.

    Attributes:
        allow_tools: If set, only tools whose name is in this set are kept;
            everything else is removed.  ``None`` means "allow all except
            ``deny_tools`` / the trust deny-list".
        deny_tools: Exact tool names removed before the run.
        deny_substrings: Case-insensitive substrings; a tool whose name
            contains any of them is removed (used by the ``untrusted`` tier).
    """

    allow_tools: Optional[Set[str]] = None
    deny_tools: Set[str] = field(default_factory=set)
    deny_substrings: List[str] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        """``True`` when the policy would never remove any tool."""
        return (
            self.allow_tools is None
            and not self.deny_tools
            and not self.deny_substrings
        )

    @staticmethod
    def _tool_name(tool: Any) -> str:
        """Best-effort name for a tool (matches Agent's own resolution)."""
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            return name
        dunder = getattr(tool, "__name__", None)
        if isinstance(dunder, str) and dunder:
            return dunder
        if isinstance(tool, dict):
            fn = tool.get("function")
            if isinstance(fn, dict) and isinstance(fn.get("name"), str):
                return fn["name"]
            top = tool.get("name")
            if isinstance(top, str) and top:
                return top
        return str(tool)

    def is_tool_allowed(self, tool: Any) -> bool:
        """Return ``True`` if ``tool`` may be exposed on this route."""
        name = self._tool_name(tool)
        if name in self.deny_tools:
            return False
        lowered = name.lower()
        for needle in self.deny_substrings:
            if needle and needle.lower() in lowered:
                return False
        if self.allow_tools is not None and name not in self.allow_tools:
            return False
        return True

    def filter_tools(self, tools: Optional[List[Any]]) -> List[Any]:
        """Return a copy of ``tools`` with denied/disallowed tools removed."""
        if not tools:
            return []
        return [tool for tool in tools if self.is_tool_allowed(tool)]


# ---------------------------------------------------------------------------
# Inbound route binding (Issue #2225)
# ---------------------------------------------------------------------------

@dataclass
class RouteBinding:
    """A single declarative inbound-routing rule.

    A binding maps a set of optional inbound conditions to a handling agent.
    Bindings are evaluated most-specific-first so operators get deterministic,
    debuggable routing across a fleet of agents behind one gateway.

    All condition fields are optional; ``None`` means "do not constrain on this
    field". A binding matches a set of :class:`RouteFacts` only when *every*
    non-``None`` condition equals the corresponding fact.

    Attributes:
        agent: The agent id to route to when this binding matches.
        chat_type: Chat type ("dm" | "group" | "channel").
        peer: Sender/user id (most specific).
        role: Role / guild-role membership of the sender.
        channel_id: Specific chat/channel id.
        account: Receiving bot account (for multi-account channels).
        priority: Higher wins; ties are broken by specificity then order.
        trust: Optional trust tier ("untrusted" | "standard" | "trusted").
            ``untrusted`` advertises a conservative, read-only-leaning toolset
            to the model so dangerous tools are never offered on third-party /
            stranger / generic-webhook routes (Issue #2298). ``None`` /
            ``standard`` / ``trusted`` apply no tier deny-list.
        allow_tools: If set, only these tool names are exposed on this route.
        deny_tools: Tool names removed before the run on this route.
    """

    agent: str
    chat_type: Optional[str] = None
    peer: Optional[str] = None
    role: Optional[str] = None
    channel_id: Optional[str] = None
    account: Optional[str] = None
    priority: int = 0
    trust: Optional[str] = None
    allow_tools: Optional[List[str]] = None
    deny_tools: Optional[List[str]] = None

    # Specificity weights — exact peer beats role/channel beats account
    # beats chat-type. Higher means more specific.
    _SPECIFICITY = {
        "peer": 16,
        "role": 8,
        "channel_id": 8,
        "account": 4,
        "chat_type": 2,
    }

    def __post_init__(self) -> None:
        """Normalise ``trust`` so config typos cannot silently fail open.

        Whitespace/case variants of a known tier (e.g. ``" Untrusted "``) are
        canonicalised. Any *unknown* non-empty value is treated as the most
        restrictive tier (``untrusted``) rather than as "no policy", so a
        misconfigured route can never accidentally expose the full toolset.
        """
        if self.trust is None:
            return
        normalized = str(self.trust).strip().lower()
        if not normalized:
            self.trust = None
        elif normalized in TRUST_TIERS:
            self.trust = normalized
        else:
            self.trust = "untrusted"

    @property
    def specificity(self) -> int:
        """Sum of weights for the conditions this binding constrains on."""
        score = 0
        for field_name, weight in self._SPECIFICITY.items():
            if getattr(self, field_name) is not None:
                score += weight
        return score

    def matches(self, facts: "RouteFacts") -> bool:
        """Return True if every constrained condition equals the facts."""
        if self.peer is not None and str(self.peer) != str(facts.peer):
            return False
        if self.channel_id is not None and str(self.channel_id) != str(facts.channel_id):
            return False
        if self.account is not None and str(self.account) != str(facts.account):
            return False
        if self.chat_type is not None and self.chat_type != facts.chat_type:
            return False
        if self.role is not None:
            expected_role = str(self.role)
            if expected_role not in [str(role) for role in (facts.roles or [])]:
                return False
        return True

    def tool_policy(self) -> Optional["ToolPolicy"]:
        """Build the :class:`ToolPolicy` this binding declares, if any.

        Returns ``None`` when the binding does not constrain the toolset, so
        callers can cheaply skip the apply/restore dance for trusted routes.
        The ``untrusted`` trust tier seeds a conservative substring deny-list;
        explicit ``allow_tools`` / ``deny_tools`` layer on top of it.
        """
        deny_substrings: List[str] = []
        if self.trust == "untrusted":
            deny_substrings = list(UNTRUSTED_DENY_SUBSTRINGS)

        allow = set(self.allow_tools) if self.allow_tools else None
        deny = set(self.deny_tools) if self.deny_tools else set()

        if allow is None and not deny and not deny_substrings:
            return None
        return ToolPolicy(
            allow_tools=allow,
            deny_tools=deny,
            deny_substrings=deny_substrings,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouteBinding":
        """Create a binding from a YAML/dict mapping.

        Accepts ``agent`` (required). Unknown keys are ignored so the shape
        can evolve without breaking older configs.
        """
        return cls(
            agent=data.get("agent", "default"),
            chat_type=data.get("chat_type"),
            peer=_as_opt_str(data.get("peer")),
            role=data.get("role"),
            channel_id=_as_opt_str(data.get("channel_id")),
            account=_as_opt_str(data.get("account")),
            priority=int(data.get("priority", 0) or 0),
            trust=_as_opt_str(data.get("trust")),
            allow_tools=_as_opt_str_list(data.get("allow_tools")),
            deny_tools=_as_opt_str_list(data.get("deny_tools")),
        )


@dataclass
class RouteFacts:
    """Inbound facts extracted from a message, used to resolve a binding.

    Attributes:
        chat_type: Normalised chat type ("dm" | "group" | "channel" | "default").
        peer: Sender/user id.
        roles: Roles/guild-role memberships of the sender.
        channel_id: The chat/channel id the message arrived in.
        account: The receiving bot account (multi-account channels).
    """

    chat_type: str = "default"
    peer: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    channel_id: Optional[str] = None
    account: Optional[str] = None


@dataclass
class RouteMatch:
    """Result of resolving a route.

    Attributes:
        agent: The resolved agent id.
        binding: The binding that matched, or ``None`` when the fallback was used.
        reason: Short human-readable explanation for logging/debugging.
    """

    agent: str
    binding: Optional[RouteBinding] = None
    reason: str = ""


def _as_opt_str(value: Any) -> Optional[str]:
    """Coerce a value to a string, preserving ``None``."""
    if value is None:
        return None
    return str(value)


def _as_opt_str_list(value: Any) -> Optional[List[str]]:
    """Coerce a YAML scalar or sequence into ``Optional[List[str]]``.

    Accepts a single string (wrapped into a one-element list) or any iterable
    of values; returns ``None`` for ``None``/empty so an absent key stays
    unconstrained.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return [value] if value else None
    try:
        items = [str(v) for v in value]
    except TypeError:
        return [str(value)]
    return items or None


def resolve_route(
    bindings: List[RouteBinding],
    facts: RouteFacts,
    default_agent: str = "default",
) -> RouteMatch:
    """Resolve the handling agent from priority-ordered bindings.

    Bindings are evaluated most-specific-first: the matching binding with the
    highest ``priority`` wins; ties are broken by specificity (exact peer →
    role/channel → account → chat-type), then by declaration order.

    Args:
        bindings: Candidate route bindings (any order).
        facts: Inbound facts extracted from the message.
        default_agent: Agent id to fall back to when nothing matches.

    Returns:
        A :class:`RouteMatch` with the selected agent and matched binding.
    """
    best: Optional[RouteBinding] = None
    best_key: tuple = ()
    for idx, binding in enumerate(bindings):
        if not binding.matches(facts):
            continue
        # Higher priority wins, then higher specificity, then earlier order.
        key = (binding.priority, binding.specificity, -idx)
        if best is None or key > best_key:
            best = binding
            best_key = key

    if best is not None:
        return RouteMatch(
            agent=best.agent,
            binding=best,
            reason=(
                f"matched binding (priority={best.priority}, "
                f"specificity={best.specificity})"
            ),
        )

    return RouteMatch(
        agent=default_agent,
        binding=None,
        reason="no binding matched; using default",
    )


# ---------------------------------------------------------------------------
# Auth Mode protocols and helpers (bind-aware authentication posture)
# ---------------------------------------------------------------------------

AuthMode = Literal["local", "token", "password", "trusted-proxy"]
"""Authentication mode for gateway/UI components.

- "local": Permissive mode for loopback interfaces (127.0.0.1, localhost, ::1)
- "token": Token-based authentication required (default for external interfaces)  
- "password": Username/password authentication
- "trusted-proxy": Authentication handled by upstream proxy
"""


def is_loopback(host: str) -> bool:
    """Check if a host is a loopback interface.
    
    Args:
        host: Host/IP address to check
        
    Returns:
        True if the host is a loopback address
        
    Examples:
        >>> is_loopback("127.0.0.1")
        True
        >>> is_loopback("localhost") 
        True
        >>> is_loopback("::1")
        True
        >>> is_loopback("0.0.0.0")
        False
        >>> is_loopback("192.168.1.1")
        False
    """
    import ipaddress
    
    # Handle localhost specially
    if host in ("localhost", "0:0:0:0:0:0:0:1"):
        return True
    
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback
    except ValueError:
        # Not a valid IP address (e.g., domain name)
        return False


def resolve_auth_mode(bind_host: str, configured: Optional[AuthMode] = None) -> AuthMode:
    """Resolve authentication mode based on bind host and explicit configuration.
    
    Args:
        bind_host: Host/IP that the service is bound to
        configured: Explicitly configured auth mode (takes precedence)
        
    Returns:
        The resolved authentication mode
        
    Examples:
        >>> resolve_auth_mode("127.0.0.1")
        'local'
        >>> resolve_auth_mode("0.0.0.0")  
        'token'
        >>> resolve_auth_mode("127.0.0.1", "token")
        'token'
    """
    if configured is not None:
        return configured
    
    return "local" if is_loopback(bind_host) else "token"


# ---------------------------------------------------------------------------
# Auth, Pairing, and Session Binding Protocols (Issue #1588 Gap 3)
# ---------------------------------------------------------------------------

@runtime_checkable
class AuthProtocol(Protocol):
    """Protocol for authentication implementations.
    
    Enables structural typing for different authentication strategies
    (token-based, local loopback, trusted proxy, etc.).
    """
    
    def check(self, request: Any) -> Dict[str, Any]:
        """Check authentication for a request.
        
        Args:
            request: The request object to authenticate
            
        Returns:
            Authentication decision with metadata:
            - success: bool - whether authentication succeeded
            - user_id: Optional[str] - authenticated user ID
            - role: Optional[str] - user role/permissions
            - metadata: Dict[str, Any] - additional auth context
        """
        ...


@runtime_checkable  
class PairingProtocol(Protocol):
    """Protocol for channel pairing implementations.
    
    Manages the authorization of external channels (Telegram, Slack, UI)
    to communicate with the gateway through signed codes.
    """
    
    def generate_code(
        self, 
        channel_type: str = "unknown", 
        channel_id: Optional[str] = None
    ) -> str:
        """Generate a new pairing code for a channel.
        
        Args:
            channel_type: Type of channel (e.g., "telegram", "slack", "ui")
            channel_id: Optional channel identifier
            
        Returns:
            The generated pairing code
        """
        ...
    
    def approve(
        self, 
        channel_type: str,
        code: str,
        user_id: str = "",
        user_name: str = ""
    ) -> bool:
        """Approve a pairing code, authorizing the channel.
        
        Args:
            channel_type: Type of channel
            code: The pairing code to approve
            user_id: User identifier (optional, defaults to empty string)
            user_name: Human-readable username (optional, defaults to empty string)
            
        Returns:
            True if approval successful, False if code invalid/expired
        """
        ...
    
    def is_paired(self, channel_id: str, channel_type: str) -> bool:
        """Check if a channel is authorized.
        
        Args:
            channel_id: Channel identifier
            channel_type: Type of channel
            
        Returns:
            True if channel is paired/authorized
        """
        ...
    
    def list_paired(self) -> List["PairedChannel"]:
        """List all authorized channels.
        
        Returns:
            List of paired channel information
        """
        ...
    
    def revoke(self, channel_id: str, channel_type: str) -> bool:
        """Revoke authorization for a channel.
        
        Args:
            channel_id: Channel identifier
            channel_type: Type of channel
            
        Returns:
            True if revocation successful, False if not found
        """
        ...
    
    def list_pending(self, channel_type: Optional[str] = None) -> List[Dict[str, any]]:
        """List pending pairing requests.
        
        Args:
            channel_type: Optional filter by channel type
            
        Returns:
            List of pending requests with channel, code, user info, and age
        """
        ...


@runtime_checkable
class SessionBindingProtocol(Protocol):
    """Protocol for session binding implementations.
    
    Manages the association between sessions and authenticated principals
    (users, agents, etc.) for state tracking and authorization.
    """
    
    def bind(self, session_id: str, principal: Dict[str, Any]) -> None:
        """Bind a session to an authenticated principal.
        
        Args:
            session_id: Unique session identifier
            principal: Principal information (user_id, roles, metadata, etc.)
        """
        ...
    
    def lookup(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Look up the principal bound to a session.
        
        Args:
            session_id: Session identifier to look up
            
        Returns:
            Principal information if found, None otherwise
        """
        ...


# Home Channel and Delivery Routing Protocols
# ---------------------------------------------------------------------------

@runtime_checkable
class HomeChannelRegistryProtocol(Protocol):
    """Protocol for managing default delivery targets per platform.
    
    Home channels provide a per-platform default delivery target that can be
    set once from inside a chat and persisted, so scheduled jobs can deliver
    results without requiring explicit channel IDs.
    """
    
    def set_home(
        self, 
        platform: str, 
        chat_id: str, 
        thread_id: Optional[str] = None
    ) -> None:
        """Set the home channel for a platform.
        
        Args:
            platform: Platform name (e.g., "telegram", "slack", "discord")
            chat_id: Platform-specific chat/channel ID
            thread_id: Optional thread ID for threaded platforms
        """
        ...
    
    def get_home(self, platform: str) -> Optional[tuple[str, Optional[str]]]:
        """Get the home channel for a platform.
        
        Args:
            platform: Platform name to look up
            
        Returns:
            Tuple of (chat_id, thread_id) if set, None otherwise
        """
        ...
    
    def platforms_with_home(self) -> List[str]:
        """List all platforms that have a home channel configured.
        
        Returns:
            List of platform names with home channels
        """
        ...


@runtime_checkable
class DeliveryResolverProtocol(Protocol):
    """Protocol for resolving delivery routing tokens.
    
    Resolves tokens like "origin", "telegram", "all" to concrete delivery
    targets at fire time, enabling ergonomic routing without hard-coded IDs.
    """
    
    def resolve(
        self, 
        token: str, 
        *, 
        origin: Optional["DeliveryTarget"] = None
    ) -> List["DeliveryTarget"]:
        """Resolve a routing token to concrete delivery targets.
        
        Token formats:
        - "origin": Reply to the chat where the job was created (requires origin)
        - "<platform>": That platform's home channel
        - "<platform>:<chat_id>[:<thread_id>]": Explicit target
        - "all": Fan-out to every connected platform with a home channel
        
        Args:
            token: Routing token to resolve
            origin: Original delivery target (for "origin" token)
            
        Returns:
            List of concrete delivery targets
        """
        ...


# ---------------------------------------------------------------------------
# Agent-facing outbound messaging (Issue #2183)
# ---------------------------------------------------------------------------

@dataclass
class DeliveryResult:
    """Outcome of an agent-initiated proactive send.

    Attributes:
        ok: Whether the send was accepted for delivery.
        target: The resolved target the message was routed to.
        summary: Human-readable summary suitable for returning to the model.
        detail: Optional extra information (error text, message id, etc.).
    """

    ok: bool
    target: str = ""
    summary: str = ""
    detail: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "ok": self.ok,
            "target": self.target,
            "summary": self.summary,
            "detail": self.detail,
        }


@dataclass
class TargetInfo:
    """A reachable delivery target the agent can address.

    Attributes:
        target: The token to pass to ``send`` (e.g. "origin", "slack:#ops").
        platform: Platform name (e.g. "telegram", "slack").
        kind: Target kind ("origin", "home", or "alias").
        label: Friendly label for display to the model/user.
    """

    target: str
    platform: str = ""
    kind: str = "alias"
    label: str = ""

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary."""
        return {
            "target": self.target,
            "platform": self.platform,
            "kind": self.kind,
            "label": self.label,
        }


@runtime_checkable
class OutboundMessengerProtocol(Protocol):
    """Protocol for agent-facing proactive message delivery.

    A concrete implementation is provided by the running gateway/bot (in the
    praisonai wrapper) and registered into the per-turn context so the
    built-in ``send_message`` tool can resolve it. It bridges to the existing
    delivery stack (DeliveryRouter, HomeChannelRegistry, outbox, mirroring).

    Example usage (implementation in praisonai_bot.gateway)::

        messenger = BotOutboundMessenger(bot, resolver, router)
        token = register_outbound_messenger(messenger)
        try:
            ...  # agent runs; send_message tool resolves the messenger
        finally:
            clear_outbound_messenger(token)
    """

    async def send(
        self,
        target: str,
        text: str,
        *,
        media: Optional[List[str]] = None,
    ) -> "DeliveryResult":
        """Deliver a message to a symbolic target.

        Args:
            target: Symbolic target token ("origin", "<platform>",
                "<platform>:<chat_id>[:<thread_id>]", or a friendly alias).
            text: The message text to send.
            media: Optional list of local file paths to attach.

        Returns:
            A :class:`DeliveryResult` describing the outcome.
        """
        ...

    def list_targets(self) -> List["TargetInfo"]:
        """List the targets currently reachable from this runtime."""
        ...


# ---------------------------------------------------------------------------
# Outbound send-policy guard (Issue #2226)
#
# ``send_message`` lets the model choose where to deliver. Because the target
# is model-controlled, poisoned inbound content (prompt injection) can steer an
# agent into delivering to a channel the operator never intended. The router
# only fails on *unresolvable* targets — a reachability check, not an
# authorisation one. This policy seam sits in core, *before* dispatch, so every
# messenger implementation is constrained, not just one adapter. Absent a
# policy, today's behaviour is preserved (allow-all).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SendDecision:
    """Closed decision shape for an outbound send-policy evaluation.

    Attributes:
        allow: Whether the send to the requested target is permitted.
        reason: Optional model-readable explanation (used in the
            :class:`DeliveryResult` detail when denied).
    """

    allow: bool
    reason: str = ""


@runtime_checkable
class SendPolicyProtocol(Protocol):
    """Protocol for authorising agent-initiated proactive sends.

    Implementations decide whether an agent may deliver to a model-chosen
    ``target``. The hook is evaluated inside the ``send_message`` path before
    the messenger dispatches, so a denied send returns a clean, model-readable
    :class:`DeliveryResult` (``ok=False``) rather than delivering.

    A concrete, config-driven implementation (:class:`SendPolicy`) is provided
    for the common allow/deny case; richer back-ends may live in plugins.
    """

    def evaluate(
        self,
        target: str,
        *,
        agent_id: str = "",
        session_id: str = "",
        origin: Optional[str] = None,
    ) -> SendDecision:
        """Return a :class:`SendDecision` for the requested ``target``."""
        ...


class SendPolicy:
    """A lightweight allow/deny send-policy with an optional default-deny posture.

    This is the config-driven default referenced by ``send_policy`` blocks in
    ``gateway.yaml`` and the ``Bot(..., send_policy=...)`` Python surface. It is
    intentionally minimal (no heavy dependencies) and lives in core so the
    built-in ``send_message`` path is always interceptable.

    Matching is exact against the symbolic target token (e.g. ``"origin"``,
    ``"slack:#ops"``, or a friendly alias). With ``default="deny"`` only listed
    targets are permitted; with ``default="allow"`` all targets are permitted
    except those in ``deny``.

    Example::

        # default-deny: only the conversation origin and an ops alias allowed
        SendPolicy(default="deny", allow=["origin", "ops-alerts"])
        # default-allow: everything permitted except an exec channel
        SendPolicy(default="allow", deny=["slack:#exec"])
    """

    def __init__(
        self,
        default: str = "allow",
        allow: Optional[List[str]] = None,
        deny: Optional[List[str]] = None,
    ):
        default = (default or "allow").lower()
        if default not in ("allow", "deny"):
            raise ValueError(
                f"send_policy default must be 'allow' or 'deny', got {default!r}"
            )
        self.default = default
        self.allow = list(allow or [])
        self.deny = list(deny or [])

    def evaluate(
        self,
        target: str,
        *,
        agent_id: str = "",
        session_id: str = "",
        origin: Optional[str] = None,
    ) -> SendDecision:
        if target in self.deny:
            return SendDecision(
                allow=False,
                reason=f"target '{target}' is denied by send_policy",
            )
        if self.default == "deny":
            if target in self.allow:
                return SendDecision(allow=True)
            return SendDecision(
                allow=False,
                reason=f"target '{target}' is not permitted by send_policy",
            )
        return SendDecision(allow=True)


# ---------------------------------------------------------------------------
# Gateway idle-dormancy / scale-to-zero (Issue #2332)
# ---------------------------------------------------------------------------


@dataclass
class IdleDecision:
    """Result of an idle/quiesce evaluation.

    Attributes:
        idle: Whether the gateway is currently quiescent.
        reason: Optional human-readable explanation (logged on quiesce).
    """

    idle: bool
    reason: str = ""


@runtime_checkable
class GatewayIdlePolicyProtocol(Protocol):
    """Protocol for gateway-process idle/scale-to-zero decisions.

    Pure, import-free decision contract consumed by the wrapper's
    ``BotOS`` run-loop. The wrapper supplies live facts (running turns,
    last inbound timestamp, background-work flag) and the policy decides
    whether the whole gateway may safely stand down. Concrete drivers
    (suspend the compute host, stand transports down, register a wake
    URL) live in the wrapper; this contract keeps the *decision* testable
    in isolation without a live gateway.

    A config-driven default (:class:`ScaleToZeroPolicy`) is provided for
    the common "idle for N minutes with nothing in flight" case.
    """

    def should_arm(
        self,
        *,
        transports_quiescable: bool,
        wake_registered: bool,
    ) -> bool:
        """Return whether dormancy may be armed at all.

        Implementations gate on whether transports can be cleanly stood
        down and a wake path exists, so a gateway never quiesces into a
        state it cannot resume from.
        """
        ...

    def is_idle(
        self,
        *,
        running_turns: int,
        last_inbound_ts: float,
        has_background_work: bool,
        now: float,
    ) -> IdleDecision:
        """Return an :class:`IdleDecision` for the supplied facts."""
        ...


class ScaleToZeroPolicy:
    """Config-driven idle policy for safe scale-to-zero.

    The default referenced by ``scale_to_zero:`` blocks in ``gateway.yaml``
    and the ``BotOS(..., idle_policy=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in
    core and is provable in isolation; the wrapper owns the side effects
    (suspend host, stand transports down, wake endpoint).

    The gateway is considered idle only when *all* guards pass:

    * no in-flight agent turn (``running_turns == 0``),
    * no live background work (scheduled jobs, delegated subagents,
      durable outbox drains — ``has_background_work`` is ``False``),
    * no inbound message for at least ``idle_timeout_minutes``.

    Example::

        ScaleToZeroPolicy(idle_timeout_minutes=5,
                          wake_url="https://my-bot.fly.dev/_wake")
    """

    def __init__(
        self,
        idle_timeout_minutes: float = 5.0,
        wake_url: Optional[str] = None,
        enabled: bool = True,
    ):
        if idle_timeout_minutes <= 0:
            raise ValueError(
                f"idle_timeout_minutes must be > 0, got {idle_timeout_minutes!r}"
            )
        self.idle_timeout_minutes = float(idle_timeout_minutes)
        self.wake_url = wake_url
        self.enabled = bool(enabled)

    @property
    def idle_timeout_seconds(self) -> float:
        return self.idle_timeout_minutes * 60.0

    def should_arm(
        self,
        *,
        transports_quiescable: bool,
        wake_registered: bool,
    ) -> bool:
        if not self.enabled:
            return False
        # Never arm into a state we cannot resume from.
        return bool(transports_quiescable and wake_registered)

    def is_idle(
        self,
        *,
        running_turns: int,
        last_inbound_ts: float,
        has_background_work: bool,
        now: float,
    ) -> IdleDecision:
        if not self.enabled:
            return IdleDecision(idle=False, reason="scale_to_zero disabled")
        if running_turns > 0:
            return IdleDecision(
                idle=False,
                reason=f"{running_turns} agent turn(s) in flight",
            )
        if has_background_work:
            return IdleDecision(
                idle=False,
                reason="background work in progress",
            )
        elapsed = now - last_inbound_ts
        if elapsed < self.idle_timeout_seconds:
            remaining = self.idle_timeout_seconds - elapsed
            return IdleDecision(
                idle=False,
                reason=f"last inbound {elapsed:.0f}s ago; {remaining:.0f}s to idle",
            )
        return IdleDecision(
            idle=True,
            reason=f"idle for {elapsed:.0f}s with nothing in flight",
        )


# Backward-compatible alias. The canonical name follows the repo's
# ``*Protocol`` suffix convention (e.g. ``SendPolicyProtocol``); the old
# name is retained so existing imports keep working.
GatewayIdlePolicy = GatewayIdlePolicyProtocol


# ---------------------------------------------------------------------------
# Gateway graceful-drain on shutdown (Issue #2375)
# ---------------------------------------------------------------------------


@dataclass
class DrainDecision:
    """Result of a drain-wait evaluation.

    Attributes:
        keep_draining: Whether to keep waiting for in-flight turns.
        reason: Optional human-readable explanation (logged at drain end).
    """

    keep_draining: bool
    reason: str = ""


@runtime_checkable
class GatewayDrainPolicyProtocol(Protocol):
    """Protocol for graceful-drain decisions on gateway shutdown.

    Pure, import-free decision contract consumed by the wrapper's
    ``BotOS`` shutdown path. On ``SIGTERM``/``SIGINT`` (rolling deploy,
    auto-update, host restart) the wrapper stops accepting new inbound
    and then repeatedly asks this policy whether to keep waiting for
    in-flight agent turns to finish, up to a bounded deadline. The
    wrapper supplies live facts (running turns, seconds elapsed); the
    policy decides whether the drain should continue. Concrete teardown
    (cancel tasks, stop transports, flush outbox) lives in the wrapper;
    this contract keeps the *wait condition* testable in isolation.

    A config-driven default (:class:`DrainTimeoutPolicy`) is provided for
    the common "wait for in-flight turns up to N seconds" case.
    """

    def should_keep_draining(
        self,
        *,
        running_turns: int,
        seconds_elapsed: float,
    ) -> DrainDecision:
        """Return a :class:`DrainDecision` for the supplied facts."""
        ...


class DrainTimeoutPolicy:
    """Config-driven graceful-drain policy for safe shutdown.

    The default referenced by ``drain_timeout`` in ``gateway.yaml`` and
    the ``BotOS(..., drain_timeout=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in
    core and is provable in isolation; the wrapper owns the side effects
    (quiesce ingress, wait, flush outbox, then tear down).

    Drain continues while *both* guards hold:

    * at least one agent turn is still in flight (``running_turns > 0``),
    * the elapsed wait is still within ``drain_timeout_seconds``.

    A ``drain_timeout_seconds`` of ``0`` disables draining entirely
    (today's behaviour: in-flight turns are cancelled immediately).

    Example::

        DrainTimeoutPolicy(drain_timeout_seconds=30)
    """

    def __init__(self, drain_timeout_seconds: float = 30.0):
        import math

        try:
            seconds = float(drain_timeout_seconds)
        except (TypeError, ValueError):
            raise ValueError(
                f"drain_timeout_seconds must be a number, got {drain_timeout_seconds!r}"
            )
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError(
                f"drain_timeout_seconds must be a finite value >= 0, "
                f"got {drain_timeout_seconds!r}"
            )
        self.drain_timeout_seconds = seconds

    def should_keep_draining(
        self,
        *,
        running_turns: int,
        seconds_elapsed: float,
    ) -> DrainDecision:
        if self.drain_timeout_seconds <= 0:
            return DrainDecision(keep_draining=False, reason="drain disabled")
        if running_turns <= 0:
            return DrainDecision(
                keep_draining=False,
                reason="no agent turns in flight",
            )
        if seconds_elapsed >= self.drain_timeout_seconds:
            return DrainDecision(
                keep_draining=False,
                reason=(
                    f"drain timeout: {running_turns} turn(s) still in flight "
                    f"after {seconds_elapsed:.0f}s"
                ),
            )
        return DrainDecision(
            keep_draining=True,
            reason=f"{running_turns} turn(s) in flight; draining",
        )


# ---------------------------------------------------------------------------
# Gateway inbound admission control (Issue #2454)
#
# The gateway protects the *outbound* path (slow-consumer eviction, bounded
# send queues, send-rate limiting) and serialises runs *per user*, but it has
# no gateway-wide ceiling on concurrent inbound agent runs. A burst of inbound
# traffic from many distinct users therefore translates directly into a burst
# of concurrent provider calls, with no admission gate in front of it.
#
# This is the pure, import-free decision contract for an admission gate. The
# wrapper's run-dispatch path (``BotSessionManager.chat``) supplies live facts
# (in-flight and queued counts) and the policy returns an ``AdmissionDecision``:
# admit now, queue (wait for capacity), or reject (busy ack). A config-driven
# default (:class:`ConcurrencyLimitPolicy`) is provided for the common bounded
# concurrency + bounded queue case; the wrapper owns the semaphore/queue
# mechanism (it needs the running event loop), this owns the *decision*.
# ---------------------------------------------------------------------------


class AdmissionDecision(str, Enum):
    """Outcome of an inbound admission evaluation.

    * ``ADMIT`` — capacity is available; run immediately.
    * ``QUEUE`` — at the concurrency ceiling but the wait queue has room;
      block until a slot frees up.
    * ``REJECT`` — over capacity and the queue is full; shed the run with a
      busy acknowledgement (a ``503``-style signal to the user).
    """

    ADMIT = "admit"
    QUEUE = "queue"
    REJECT = "reject"


@runtime_checkable
class GatewayConcurrencyPolicyProtocol(Protocol):
    """Protocol for gateway-wide inbound admission decisions.

    Pure, import-free decision contract consumed by the wrapper's run-dispatch
    path. The wrapper supplies the live aggregate counts (turns currently
    in flight and turns currently waiting) and the policy decides whether the
    next inbound turn may run now, must wait, or should be shed. Concrete
    enforcement (an ``asyncio.Semaphore`` ceiling plus a bounded
    ``asyncio.Queue`` with per-session fairness) lives in the wrapper, since it
    needs the running event loop and live session manager; this contract keeps
    the *decision* testable in isolation.

    A config-driven default (:class:`ConcurrencyLimitPolicy`) is provided for
    the common "N concurrent runs, bounded wait queue, declared overflow"
    case.
    """

    max_concurrent_runs: int
    queue_depth: int

    def decide(
        self,
        *,
        in_flight: int,
        queued: int,
        session_id: str = "",
    ) -> AdmissionDecision:
        """Return an :class:`AdmissionDecision` for the supplied facts."""
        ...


class ConcurrencyLimitPolicy:
    """Config-driven inbound admission policy for a bounded gateway.

    The default referenced by ``gateway.max_concurrent_runs`` /
    ``gateway.queue_depth`` / ``gateway.overflow_policy`` in ``gateway.yaml``
    and the ``BotOS(..., max_concurrent_runs=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in core and
    is provable in isolation; the wrapper owns the side effects (acquire a
    semaphore slot, enqueue/dequeue, return a busy ack).

    The decision is:

    * ``ADMIT`` while ``in_flight < max_concurrent_runs``.
    * At the ceiling, ``QUEUE`` while ``queued < queue_depth`` and the
      ``overflow_policy`` permits waiting.
    * Otherwise the ``overflow_policy`` decides the shed behaviour:
        - ``"reject"`` → :attr:`AdmissionDecision.REJECT` (busy ack).
        - ``"queue"`` → :attr:`AdmissionDecision.QUEUE` (block beyond the
          declared depth — for callers that prefer unbounded waiting to
          shedding; the wrapper still bounds the actual queue object).
        - ``"shed_oldest"`` → :attr:`AdmissionDecision.QUEUE`; the wrapper
          drops the oldest waiter to make room rather than rejecting the new
          arrival.

    A ``max_concurrent_runs`` of ``0`` disables admission control entirely
    (today's behaviour: every inbound turn is admitted immediately).

    Example::

        ConcurrencyLimitPolicy(max_concurrent_runs=32, queue_depth=128,
                               overflow_policy="reject")
    """

    _OVERFLOW = ("reject", "queue", "shed_oldest")

    def __init__(
        self,
        max_concurrent_runs: int = 0,
        queue_depth: int = 0,
        overflow_policy: str = "reject",
    ):
        try:
            ceiling = int(max_concurrent_runs)
        except (TypeError, ValueError):
            raise ValueError(
                f"max_concurrent_runs must be an integer, "
                f"got {max_concurrent_runs!r}"
            )
        if ceiling < 0:
            raise ValueError(
                f"max_concurrent_runs must be >= 0, got {max_concurrent_runs!r}"
            )
        try:
            depth = int(queue_depth)
        except (TypeError, ValueError):
            raise ValueError(
                f"queue_depth must be an integer, got {queue_depth!r}"
            )
        if depth < 0:
            raise ValueError(f"queue_depth must be >= 0, got {queue_depth!r}")
        overflow = (overflow_policy or "reject").strip().lower()
        if overflow not in self._OVERFLOW:
            raise ValueError(
                f"overflow_policy must be one of {self._OVERFLOW}, "
                f"got {overflow_policy!r}"
            )
        self.max_concurrent_runs = ceiling
        self.queue_depth = depth
        self.overflow_policy = overflow

    @property
    def enabled(self) -> bool:
        """Whether admission control is active (a positive ceiling is set)."""
        return self.max_concurrent_runs > 0

    def decide(
        self,
        *,
        in_flight: int,
        queued: int,
        session_id: str = "",
    ) -> AdmissionDecision:
        # Disabled: preserve legacy always-admit behaviour.
        if self.max_concurrent_runs <= 0:
            return AdmissionDecision.ADMIT
        if in_flight < self.max_concurrent_runs:
            return AdmissionDecision.ADMIT
        # At the ceiling: consult the bounded wait queue.
        if queued < self.queue_depth:
            return AdmissionDecision.QUEUE
        # Queue is full: declared overflow behaviour.
        if self.overflow_policy == "queue":
            # Caller opted into waiting beyond the declared depth.
            return AdmissionDecision.QUEUE
        if self.overflow_policy == "shed_oldest":
            # Make room by dropping the oldest waiter (wrapper enforces).
            return AdmissionDecision.QUEUE
        return AdmissionDecision.REJECT


# Backward-compatible alias following the repo's ``*Protocol`` convention.
GatewayConcurrencyPolicy = GatewayConcurrencyPolicyProtocol


# ---------------------------------------------------------------------------
# Gateway rate-limit admission (Issue #2532)
#
# Rate limiting completes the gateway's policy-protocol family (send, idle,
# drain, concurrency). Like its siblings it is a pure, import-free decision
# over typed facts — an identity, a scope (endpoint class / channel / tenant)
# and a timestamp — returning a closed :class:`RateLimitDecision`. Core ships
# a config-driven sliding-window default (:class:`SlidingWindowRateLimitPolicy`)
# that reproduces today's built-in behaviour; the wrapper limiters adopt the
# protocol and developers can inject their own (per-tenant, distributed,
# cost-based) without importing wrapper internals. Core maps a ``limited``
# decision onto ``ConnectErrorCode.RATE_LIMITED`` +
# ``HelloError.retry_after_seconds``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a rate-limit evaluation.

    Attributes:
        allowed: Whether the request may proceed.
        retry_after_seconds: Backoff hint populated when ``allowed`` is
            ``False`` (seconds until the caller may retry); ``None`` when
            allowed.
    """

    allowed: bool
    retry_after_seconds: Optional[float] = None


@runtime_checkable
class RateLimitPolicyProtocol(Protocol):
    """Protocol for gateway rate-limit / throttle admission decisions.

    Pure, import-free decision contract consumed by the wrapper's admission
    paths. The wrapper supplies typed facts (the caller ``identity``, the
    ``scope`` — an endpoint class, channel, or tenant token — and the current
    ``now`` timestamp) and the policy decides whether the request is allowed
    or ``limited`` with a ``retry_after_seconds`` hint. Concrete state and
    enforcement (sliding windows, token buckets, a Redis-backed per-tenant
    quota) live in the implementation; this contract keeps the *decision*
    injectable and testable in isolation, symmetric with
    :class:`SendPolicyProtocol` / :class:`GatewayConcurrencyPolicyProtocol`.

    A config-driven default (:class:`SlidingWindowRateLimitPolicy`) is
    provided for the common "N requests per window per identity" case; core
    maps a ``limited`` decision onto ``ConnectErrorCode.RATE_LIMITED`` and
    ``HelloError.retry_after_seconds``.
    """

    def check(
        self,
        *,
        identity: str,
        scope: str,
        now: float,
    ) -> RateLimitDecision:
        """Return a :class:`RateLimitDecision` for the supplied facts."""
        ...


class SlidingWindowRateLimitPolicy:
    """Config-driven sliding-window rate-limit policy.

    The default referenced by ``gateway.rate_limit`` blocks in
    ``gateway.yaml`` and the ``WebSocketGateway(..., rate_limit_policy=...)``
    Python surface. It is intentionally minimal and dependency-free so the
    decision lives in core and is provable in isolation; heavy wrapper
    limiters (``gateway/rate_limiter.py`` sliding window,
    ``bots/_rate_limit.py`` token bucket) may adopt this protocol while
    keeping their own state and side effects.

    The decision, keyed by ``(scope, identity)``:

    * ``allowed`` while fewer than ``max_requests`` have been seen in the
      current ``window_seconds`` window.
    * Once the window count exceeds ``max_requests``, the key enters a
      ``lockout_seconds`` cooldown and every :meth:`check` returns
      ``allowed=False`` with a ``retry_after_seconds`` hint until it elapses.

    A ``max_requests`` of ``0`` disables limiting entirely (every request is
    allowed) — the legacy default when no rate limit is configured.

    This class is not internally synchronised; the wrapper owns any locking
    it needs for concurrent hot paths (the built-in limiters already do).

    State ownership: per-``(scope, identity)`` window/lockout entries are
    reclaimed lazily — a key's entry is dropped or overwritten the next time
    that key is checked. It keeps one entry per *active* key and is intended
    for a bounded identity space (endpoint classes, authenticated tenants). A
    wrapper exposing it to an unbounded/untrusted identity space (e.g. raw
    per-IP keys) owns periodic reclamation, exactly as it owns locking.

    Example::

        SlidingWindowRateLimitPolicy(max_requests=5, window_seconds=60,
                                     lockout_seconds=300)
    """

    def __init__(
        self,
        max_requests: int = 0,
        window_seconds: float = 60.0,
        lockout_seconds: float = 0.0,
    ):
        try:
            ceiling = int(max_requests)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"max_requests must be an integer, got {max_requests!r}"
            ) from err
        if ceiling < 0:
            raise ValueError(f"max_requests must be >= 0, got {max_requests!r}")
        try:
            window = float(window_seconds)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"window_seconds must be a number, got {window_seconds!r}"
            ) from err
        if window <= 0:
            raise ValueError(
                f"window_seconds must be > 0, got {window_seconds!r}"
            )
        try:
            lockout = float(lockout_seconds)
        except (TypeError, ValueError) as err:
            raise ValueError(
                f"lockout_seconds must be a number, got {lockout_seconds!r}"
            ) from err
        if lockout < 0:
            raise ValueError(
                f"lockout_seconds must be >= 0, got {lockout_seconds!r}"
            )
        self.max_requests = ceiling
        self.window_seconds = window
        self.lockout_seconds = lockout
        # (scope, identity) -> (window_start, count)
        self._windows: Dict[Tuple[str, str], Tuple[float, int]] = {}
        # (scope, identity) -> lockout_expires_at
        self._lockouts: Dict[Tuple[str, str], float] = {}

    @property
    def enabled(self) -> bool:
        """Whether limiting is active (a positive ceiling is set)."""
        return self.max_requests > 0

    def check(
        self,
        *,
        identity: str,
        scope: str,
        now: float,
    ) -> RateLimitDecision:
        # Disabled: preserve legacy always-allow behaviour.
        if self.max_requests <= 0:
            return RateLimitDecision(allowed=True)

        key = (scope, identity)

        # Active lockout?
        lockout_until = self._lockouts.get(key)
        if lockout_until is not None:
            if now < lockout_until:
                return RateLimitDecision(
                    allowed=False,
                    retry_after_seconds=max(0.0, lockout_until - now),
                )
            # Expired lockout: clear and start fresh.
            del self._lockouts[key]

        window = self._windows.get(key)
        if window is None or (now - window[0]) >= self.window_seconds:
            # New or expired window.
            self._windows[key] = (now, 1)
            return RateLimitDecision(allowed=True)

        window_start, count = window
        count += 1
        if count > self.max_requests:
            # Over the ceiling within the window.
            if self.lockout_seconds > 0:
                # Cooldown: drop the window and lock the key out until it
                # elapses.
                del self._windows[key]
                retry = self.lockout_seconds
                self._lockouts[key] = now + self.lockout_seconds
            else:
                # No cooldown: keep the window so the key stays denied until
                # it naturally expires, matching the retry hint. Deleting it
                # here would let the next check start a fresh window and be
                # allowed immediately, bypassing the ceiling.
                self._windows[key] = (window_start, count)
                retry = max(0.0, self.window_seconds - (now - window_start))
            return RateLimitDecision(
                allowed=False,
                retry_after_seconds=retry,
            )

        self._windows[key] = (window_start, count)
        return RateLimitDecision(allowed=True)


# Backward-compatible alias following the repo's ``*Protocol`` convention.
RateLimitPolicy = RateLimitPolicyProtocol


# ---------------------------------------------------------------------------
# Port-less, restart-safe external drain trigger (Issue #2390)
#
# Hosted/containerised deployments (Docker, Fly, Kubernetes) need to ask a
# *running* gateway to drain — finish active turns, stop accepting new ones,
# then exit — without exposing an inbound control port (a port is attack
# surface the gateway deliberately avoids). The mechanism is a presence-based
# marker file (e.g. ``~/.praisonai/gateway/.drain_request.json``) that a
# background watcher in the wrapper reads. The marker is stamped with an
# *instantiation epoch* (kernel boot id + PID-1 start time); a marker left
# over from a prior instantiation on a durable volume is treated as stale and
# ignored, so a rebooted instance never wedges in "draining" forever.
#
# The epoch/staleness check is a pure, testable predicate and belongs in core
# beside ``ScaleToZeroPolicy``/``DrainTimeoutPolicy``; the watcher wiring and
# the ``praisonai gateway drain`` CLI live in the wrapper.
# ---------------------------------------------------------------------------


def current_epoch() -> str:
    """Return a stable identifier for the current OS *instantiation*.

    The epoch combines the most durable, restart-distinguishing signals
    available so a drain marker can be tied to the instantiation that wrote
    it. It is derived from (best-effort, in order of preference):

    * the kernel boot id (Linux ``/proc/sys/kernel/random/boot_id``), which
      changes on every reboot, and
    * the start time of PID 1 (the init process), which also changes on every
      boot / container (re)start.

    On platforms where neither is available the function degrades gracefully
    to an empty string; callers that cannot determine an epoch should treat
    *every* marker as foreign (fail-safe: ignore stale-looking requests) by
    pairing this with :class:`DrainMarkerPolicy`, which ignores markers whose
    epoch does not match the current one.

    Returns:
        A non-secret, opaque epoch token (``"<boot_id>:<pid1_start>"``) when
        *both* signals are available, or an empty string otherwise. Requiring
        both keeps the contract fail-closed: a partial epoch (e.g. ``boot_id``
        alone, which is unchanged across same-host container restarts) could
        let a durable stale marker match a fresh instance, so it is never
        emitted.
    """
    boot_id = ""
    try:
        with open("/proc/sys/kernel/random/boot_id", "r") as fh:
            boot_id = fh.read().strip()
    except (OSError, ValueError):
        boot_id = ""

    pid1_start = ""
    try:
        # field 22 of /proc/1/stat is the process start time in clock ticks
        # since boot. Names can contain spaces/parens, so split on the final
        # ')' to reach the stable numeric tail.
        with open("/proc/1/stat", "r") as fh:
            raw = fh.read()
        tail = raw.rsplit(")", 1)[-1].split()
        # tail[0] is 'state'; field 22 overall == index 19 of the tail.
        if len(tail) > 19:
            pid1_start = tail[19]
    except (OSError, ValueError, IndexError):
        pid1_start = ""

    if boot_id and pid1_start:
        return f"{boot_id}:{pid1_start}"
    # Fail closed: a partial epoch cannot reliably distinguish a restart, so an
    # empty epoch is returned and DrainMarkerPolicy treats every marker as
    # foreign (ignored) unless ``require_epoch=False`` is set explicitly.
    return ""


class DrainMarkerPolicy:
    """Pure predicate deciding whether an external drain marker is actionable.

    A drain marker is a small JSON object written by an operator / deploy step
    (via ``praisonai gateway drain``) into a well-known path. A background
    watcher in the wrapper reads it and asks this policy whether the running
    gateway should react. The decision is intentionally side-effect free so it
    is provable in isolation without a live gateway or filesystem.

    A marker is honoured only when it requests a drain *for the current
    instantiation*:

    * a missing marker (``None``) is never a drain request;
    * a marker carrying no ``epoch`` is treated as foreign and ignored, so a
      hand-rolled or legacy file cannot wedge a process;
    * a marker whose ``epoch`` differs from ``current_epoch`` is stale — it
      survived a reboot/restart on a durable volume — and is ignored;
    * a current-epoch marker is honoured (subject to an optional
      already-handled de-duplication via ``last_handled_epoch``).

    Example::

        policy = DrainMarkerPolicy()
        if policy.drain_requested(read_marker(), current_epoch(), monotonic()):
            await gateway.stop(drain_timeout=cfg.gateway.drain_timeout)
    """

    def __init__(self, *, require_epoch: bool = True):
        self.require_epoch = bool(require_epoch)

    def drain_requested(
        self,
        marker: Optional[Dict[str, Any]],
        current_epoch: str,
        now: float,
        *,
        last_handled_epoch: Optional[str] = None,
    ) -> bool:
        """Return whether ``marker`` is a live drain request for this instance.

        Args:
            marker: Parsed marker contents, or ``None`` when no marker file is
                present.
            current_epoch: The current instantiation epoch (see
                :func:`current_epoch`).
            now: A monotonic timestamp (unused by the default policy; accepted
                so subclasses can implement TTL/debounce without changing the
                call site).
            last_handled_epoch: If supplied and equal to the marker's epoch,
                the request is treated as already handled and ignored, so a
                watcher polling repeatedly only fires once per instantiation.

        Returns:
            ``True`` only for a non-stale, current-epoch drain request that has
            not already been handled.
        """
        if not isinstance(marker, dict):
            return False

        marker_epoch = marker.get("epoch")
        if not isinstance(marker_epoch, str) or not marker_epoch:
            # No epoch stamp: cannot prove it belongs to this instantiation.
            # Fail safe by ignoring it unless epochs are explicitly optional.
            if self.require_epoch:
                return False
        elif marker_epoch != current_epoch:
            # A marker from a prior instantiation (e.g. survived a reboot on a
            # durable volume). Ignore it so a fresh instance never wedges.
            return False
        elif last_handled_epoch is not None and marker_epoch == last_handled_epoch:
            # Already acted on this instantiation's request.
            return False

        action = marker.get("action", "drain")
        if not isinstance(action, str):
            # A non-string action is a malformed marker; fail closed.
            return False
        if action.strip().lower() not in ("", "drain"):
            return False
        return True


# ---------------------------------------------------------------------------
# Crash / shutdown forensics (Issue #2436)
#
# A 24/7 gateway restarted by a supervisor (systemd/s6/Kubernetes) leaves no
# evidence of *why* it died when the death was not its own decision — OOM kill,
# supervisor ``SIGKILL``/``SIGTERM``, or a parent dying. The wrapper installs
# forensic signal handlers that capture a fast, non-blocking snapshot and spawn
# a detached diagnostic that survives a ``SIGKILL`` on the process group.
#
# The decision/formatting pieces that need no OS I/O live here as pure helpers
# beside ``ScaleToZeroPolicy``/``DrainTimeoutPolicy``/``DrainMarkerPolicy``; the
# heavy /proc reads, ``os.getrusage``/``os.getloadavg`` calls, and detached
# subprocess spawn live in the praisonai wrapper behind the protocol below.
# ---------------------------------------------------------------------------


@runtime_checkable
class ShutdownForensicsProtocol(Protocol):
    """Protocol for capturing forensics when a gateway dies unexpectedly.

    Pure contract consumed by the wrapper's signal handlers. ``snapshot``
    must be fast (<10ms), never raise, and never block the asyncio teardown;
    ``spawn_diagnostic`` is fire-and-forget and must run the diagnostic in a
    *detached* session so a ``SIGKILL`` on the process group does not also kill
    the diagnostic. Concrete OS I/O (``/proc`` reads, ``os.getrusage``,
    ``os.getloadavg``, subprocess spawn) lives in the wrapper implementation.
    """

    def snapshot(self, signal_name: Optional[str] = None) -> Dict[str, Any]:
        """Return a small, JSON-serialisable forensic context.

        Must never raise; on any internal failure it returns a best-effort
        (possibly partial) dict so the caller can still log *something*.
        """
        ...

    def spawn_diagnostic(self, ctx: Dict[str, Any], log_dir: Optional[str]) -> None:
        """Fire-and-forget a detached diagnostic into ``log_dir``.

        Must never raise and must not block the caller; the diagnostic runs in
        a detached session so it survives a ``SIGKILL`` on the process group.
        """
        ...


def format_forensics_for_log(ctx: Optional[Dict[str, Any]]) -> str:
    """Render a forensic snapshot dict as a single, stable log line.

    Pure and side-effect free so it is provable in isolation and safe to call
    from a signal handler. Unknown/missing fields are simply omitted; the
    output is a compact ``key=value`` sequence prefixed with a stable marker so
    operators (and log scrapers) can grep ``gateway-forensics`` reliably.

    Args:
        ctx: The dict returned by :meth:`ShutdownForensicsProtocol.snapshot`,
            or ``None``.

    Returns:
        A single-line, human-readable summary. Never raises.
    """
    if not isinstance(ctx, dict):
        return "gateway-forensics: <unavailable>"

    # Ordered so the most operationally useful facts come first.
    keys = (
        "signal",
        "pid",
        "ppid",
        "supervised",
        "loadavg_1m",
        "traced",
        "maxrss_kb",
    )
    parts: List[str] = []
    for key in keys:
        if key not in ctx:
            continue
        value = ctx[key]
        if value is None:
            continue
        if isinstance(value, bool):
            rendered = "yes" if value else "no"
        elif isinstance(value, float):
            rendered = f"{value:.2f}"
        else:
            rendered = str(value).replace("\n", " ").strip()
        if rendered == "":
            continue
        parts.append(f"{key}={rendered}")

    if not parts:
        return "gateway-forensics: <empty>"
    return "gateway-forensics: " + " ".join(parts)


def is_supervised(ppid: Optional[int], invocation_id: Optional[str]) -> bool:
    """Return whether the process appears to run under a service manager.

    Pure predicate. A process is considered supervised when either:

    * its parent is PID 1 (``ppid == 1`` — reparented to init / the container
      entrypoint), or
    * the systemd ``INVOCATION_ID`` environment variable is present (the unit
      was started by systemd).

    Args:
        ppid: The parent PID, or ``None`` when unavailable.
        invocation_id: The value of ``$INVOCATION_ID``, or ``None``/empty.

    Returns:
        ``True`` when either supervision signal is present.
    """
    if ppid == 1:
        return True
    return bool(invocation_id)


def drain_timeout_has_headroom(
    stop_timeout_s: Optional[float],
    drain_timeout_s: Optional[float],
    headroom_s: float = 30.0,
) -> bool:
    """Return whether the supervisor stop-timeout leaves room to drain.

    Pure predicate used by a startup sanity check. A supervisor whose
    stop-timeout is shorter than ``drain_timeout + headroom`` will ``SIGKILL``
    the gateway mid-drain, leaving no explanation. This returns ``False`` only
    when we can *prove* the headroom is insufficient; when either value is
    unknown (``None``) or non-positive it returns ``True`` (fail-open: do not
    emit a spurious warning when we cannot tell).

    Args:
        stop_timeout_s: The supervisor's configured stop-timeout in seconds, or
            ``None`` when it could not be determined.
        drain_timeout_s: The gateway's configured drain timeout in seconds, or
            ``None``/0 when draining is disabled.
        headroom_s: Slack to reserve beyond the drain window for teardown.

    Returns:
        ``True`` when there is adequate headroom (or it cannot be determined),
        ``False`` only when the stop-timeout is provably too short.
    """
    try:
        drain = float(drain_timeout_s) if drain_timeout_s is not None else 0.0
        head = float(headroom_s)
    except (TypeError, ValueError):
        return True
    if drain <= 0:
        # Draining disabled: nothing to be killed mid-drain.
        return True
    if stop_timeout_s is None:
        # Unknown supervisor timeout: cannot prove a problem.
        return True
    try:
        stop = float(stop_timeout_s)
    except (TypeError, ValueError):
        return True
    if stop <= 0:
        return True
    return stop >= drain + head


# ---------------------------------------------------------------------------
# Code-skew guard for hot operations (Issue #2460)
# ---------------------------------------------------------------------------


def detect_code_skew(
    boot_fp: Optional[str], disk_fp: Optional[str]
) -> Optional[Tuple[str, str]]:
    """Return shortened ``(boot, disk)`` fingerprints if the code changed.

    This is the pure, side-effect-free heart of the code-skew guard. It does
    not read the filesystem or git; callers pass the fingerprint captured at
    boot and a freshly-read on-disk fingerprint (see
    :func:`read_code_fingerprint`).

    The check is intentionally fail-open: if either fingerprint is unknown
    (``None`` / empty) it returns ``None`` so the caller proceeds normally and
    never blocks an operation just because the revision could not be read.

    Args:
        boot_fp: Fingerprint captured when the gateway started.
        disk_fp: Fingerprint of the code currently on disk.

    Returns:
        ``(boot_short, disk_short)`` when the running code differs from disk,
        otherwise ``None``. Git SHAs are shortened to 7 characters (including a
        leading SHA in a combined ``"<sha>+mtime:..."`` fingerprint); other
        fingerprints are returned unchanged.
    """
    if not boot_fp or not disk_fp:
        return None
    if boot_fp == disk_fp:
        return None

    def _is_sha(token: str) -> bool:
        return len(token) == 40 and all(c in "0123456789abcdef" for c in token.lower())

    def _short(fp: str) -> str:
        # Shorten bare git SHAs (40 hex chars) to the conventional 7, including
        # a leading SHA in a combined "<sha>+mtime:<ns>" fingerprint; leave
        # other fingerprint shapes (e.g. "mtime:...") untouched.
        if _is_sha(fp):
            return fp[:7]
        head, sep, tail = fp.partition("+")
        if sep and _is_sha(head):
            return f"{head[:7]}{sep}{tail}"
        return fp

    return (_short(boot_fp), _short(disk_fp))


# ---------------------------------------------------------------------------
# Restart-intent exit-code protocol (Issue #2437)
# ---------------------------------------------------------------------------
#
# When the gateway/bot process exits, its exit code is the only signal a
# process supervisor (systemd ``Restart=on-failure``, an s6 finish script,
# a Kubernetes restart policy) receives about whether coming back is worth
# it. A generic ``1`` makes a transient blip and a fatal misconfiguration
# look identical, so a misconfigured gateway crash-loops forever instead of
# stopping and surfacing the problem.
#
# These constants follow the ``sysexits.h`` convention so they compose with
# existing supervisor tooling without bespoke wrappers:
#
#   * ``EX_TEMPFAIL`` (75) — transient/restartable: ask the supervisor to
#     restart (network blip, upstream 503, intentional drain-then-restart).
#   * ``EX_CONFIG`` (78) — fatal config error: do NOT restart, fix the
#     config (duplicate token, no platforms, malformed ``gateway.yaml``,
#     invalid credentials at startup).
#
# The constants and the pure ``classify_exit_reason`` classifier live in
# core so the wrapper CLI, the runtime entry point, and any future runtime
# share one source of truth. The wrapper owns the actual ``sys.exit``.

GATEWAY_OK_EXIT_CODE = 0
"""Clean shutdown / success (EX_OK)."""

GATEWAY_RESTART_EXIT_CODE = 75
"""Transient/restartable failure — ask the supervisor to restart (EX_TEMPFAIL)."""

GATEWAY_FATAL_CONFIG_EXIT_CODE = 78
"""Fatal config error — supervisor should stop restarting; fix config (EX_CONFIG)."""


class FatalConfigError(Exception):
    """Raised on an unrecoverable gateway/bot configuration error.

    Signals that restarting the process is pointless until an operator
    fixes the configuration — e.g. two bots sharing one token, no
    messaging platform configured, a malformed ``gateway.yaml``, or an
    invalid credential detected at startup. The wrapper entry point maps
    this to :data:`GATEWAY_FATAL_CONFIG_EXIT_CODE` (78) so the supervisor
    halts the crash-loop and the failure is terminal and visible.
    """


def classify_exit_reason(exc: "BaseException | None") -> int:
    """Map an exit cause to a supervisor-friendly exit code (pure).

    The single source of truth shared by the wrapper CLI and runtime
    entry point. Side-effect free so it is provable in isolation.

    Args:
        exc: The exception that terminated the process, or ``None`` for a
            clean shutdown.

    Returns:
        * :data:`GATEWAY_OK_EXIT_CODE` (0) when ``exc`` is ``None`` or a
          ``KeyboardInterrupt``/``SystemExit(0)`` (clean stop).
        * :data:`GATEWAY_FATAL_CONFIG_EXIT_CODE` (78) for
          :class:`FatalConfigError` (do not restart — fix config).
        * :data:`GATEWAY_RESTART_EXIT_CODE` (75) for any other exception
          (transient — ask supervisor to restart).
    """
    if exc is None:
        return GATEWAY_OK_EXIT_CODE
    if isinstance(exc, KeyboardInterrupt):
        return GATEWAY_OK_EXIT_CODE
    if isinstance(exc, SystemExit):
        code = exc.code
        if code is None or code == 0:
            return GATEWAY_OK_EXIT_CODE
        return code if isinstance(code, int) else GATEWAY_RESTART_EXIT_CODE
    if isinstance(exc, FatalConfigError):
        return GATEWAY_FATAL_CONFIG_EXIT_CODE
    return GATEWAY_RESTART_EXIT_CODE


# ---------------------------------------------------------------------------
# Protocol Version Negotiation (Issue #2130)
# ---------------------------------------------------------------------------

# Protocol version constants
PROTOCOL_VERSION = 1
MIN_PROTOCOL_VERSION = 1
MAX_PROTOCOL_VERSION = 1


class ProtocolHello(TypedDict, total=False):
    """Protocol version negotiation handshake request.
    
    Sent by client during join to negotiate protocol version.
    """
    min_version: int  # Minimum protocol version client supports
    max_version: int  # Maximum protocol version client supports
    features: List[str]  # Optional feature flags


class ProtocolHelloOk(TypedDict):
    """Protocol version negotiation response.
    
    Server's response to protocol negotiation.
    """
    protocol_version: int  # Negotiated protocol version
    server_min_version: int  # Server's minimum supported version
    server_max_version: int  # Server's maximum supported version
    features: List[str]  # Enabled feature flags


class GapInfo(TypedDict):
    """Information about a gap in the event sequence."""
    expected_seq: int  # Expected sequence number
    received_seq: int  # Received sequence number  
    missed_count: int  # Number of events missed


class ResumeSnapshot(TypedDict, total=False):
    """Complete snapshot for session resumption.
    
    Provides all necessary state for one-round-trip reconnection.
    """
    cursor: int  # Resume cursor position
    sequence: int  # Current sequence number for gap detection
    events: List[Dict[str, Any]]  # Replayed events since cursor
    presence: List[Dict[str, Any]]  # Current presence information
    health: Dict[str, Any]  # Gateway health status
    session_state: Dict[str, Any]  # Session-specific state


# ──────────────────────────────────────────────────────────────────────
# Relay transport (Issue #2485)
#
# A protocol-first seam so a thin *connector* process can own the platform
# socket (Telegram/Discord/WhatsApp/...) and relay normalised inbound events
# to a gateway over an authenticated transport, while accepting outbound
# sends/interrupts back down. This decouples the *platform connection* from
# the gateway process, enabling:
#   * headless / NAT-friendly hosting (gateway needs no public inbound port),
#   * one gateway fronting many remotely-hosted connectors,
#   * lossless scale-to-zero (the connector stays connected and buffers while
#     the gateway is dormant, draining the backlog on wake).
#
# These are *protocols only* — no transport (WebSocket/gRPC/message bus) and
# no platform SDK is imported here. Concrete implementations live in the
# praisonai wrapper.
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityDescriptor:
    """A capability profile a relay connector attests at handshake time.

    Where :class:`~praisonaiagents.bots.presentation.PlatformCapabilities`
    declares capabilities *statically* in core, this descriptor is negotiated
    by a remote connector at connect time so the streaming/delivery layer can
    adapt to the actual platform the connector is fronting.

    Attributes:
        max_message_length: Maximum outbound message length the platform
            accepts before the connector must split/truncate.
        length_unit: How ``max_message_length`` is measured — ``"chars"``
            (Unicode code points) or ``"utf16"`` (UTF-16 code units, as some
            platforms count).
        supports_edit: Whether the platform supports editing a sent message
            (enables draft-streaming via in-place edits).
        supports_draft_streaming: Whether the connector can stream partial
            drafts (incremental updates) for a single turn.
        markdown_dialect: Markdown flavour the platform renders
            (e.g. ``"none"``, ``"markdown"``, ``"markdownv2"``, ``"html"``).
    """

    max_message_length: int
    length_unit: str = "chars"  # "chars" | "utf16"
    supports_edit: bool = False
    supports_draft_streaming: bool = False
    markdown_dialect: str = "none"

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a serializable dictionary (for the handshake wire)."""
        return {
            "max_message_length": self.max_message_length,
            "length_unit": self.length_unit,
            "supports_edit": self.supports_edit,
            "supports_draft_streaming": self.supports_draft_streaming,
            "markdown_dialect": self.markdown_dialect,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapabilityDescriptor":
        """Reconstruct a descriptor from its serialized form."""
        return cls(
            max_message_length=int(data["max_message_length"]),
            length_unit=str(data.get("length_unit", "chars")),
            supports_edit=bool(data.get("supports_edit", False)),
            supports_draft_streaming=bool(
                data.get("supports_draft_streaming", False)
            ),
            markdown_dialect=str(data.get("markdown_dialect", "none")),
        )


@runtime_checkable
class RelayTransport(Protocol):
    """Protocol for an out-of-process platform-connector relay.

    A concrete implementation (e.g. a ``WebSocketRelayTransport`` in the
    praisonai wrapper) lets a connector that holds the platform socket
    forward normalised inbound :class:`GatewayMessage` events to the gateway
    and accept outbound sends/interrupts back down. The gateway treats the
    relay like any other adapter (same inbound routing, admission control,
    delivery) but the connection lives elsewhere.

    Lifecycle::

        caps = await transport.connect()            # handshake → capabilities
        transport.set_inbound_handler(on_message)   # wire inbound events in
        ...                                          # events relayed in/out
        await transport.go_dormant()                 # pause, keep connection
        await transport.disconnect()                 # tear down
    """

    async def connect(self) -> "CapabilityDescriptor":
        """Establish the relay and complete the handshake.

        Returns the :class:`CapabilityDescriptor` attested by the connector
        for the platform it is fronting.
        """
        ...

    def set_inbound_handler(
        self, handler: Callable[["GatewayMessage"], Awaitable[None]]
    ) -> None:
        """Register the coroutine invoked for each relayed inbound message."""
        ...

    async def send_outbound(
        self, target: "TargetInfo", message: "GatewayMessage"
    ) -> "DeliveryResult":
        """Relay an outbound message to ``target`` via the connector."""
        ...

    async def go_dormant(self) -> None:
        """Pause inbound dispatch without dropping the connection.

        The connector keeps the platform socket open and buffers inbound
        events while the gateway is dormant (scale-to-zero), so they can be
        drained losslessly on wake.
        """
        ...

    async def disconnect(self) -> None:
        """Tear down the relay connection."""
        ...


# ---------------------------------------------------------------------------
# Gateway pipeline span-tracing seam (Issue #2716)
#
# Running a bot fleet on the gateway means debugging latency/failures across an
# async pipeline: inbound -> admission/queue -> agent turn -> each tool/LLM
# call -> outbox -> delivery. Today an operator can correlate *logs* by a
# single correlation id and read *counters* from ``/metrics``, but cannot see a
# per-turn span breakdown or error spans in a distributed tracer
# (Jaeger/Tempo/Datadog/Honeycomb).
#
# This is the missing *stage seam*: a dependency-free hook the wrapper gateway
# can fire around each pipeline stage. Core holds only the protocol and a
# zero-cost no-op default (``NullGatewayTraceHook``) so there is no OTel import
# and no hot-path overhead when tracing is disabled. A ``praisonai-plugins``
# OTel exporter implements the protocol and opens/closes real spans over OTLP,
# reusing the existing correlation id as a span attribute — keeping the heavy
# ``opentelemetry-sdk`` dependency out of core and the wrapper.
#
# The seam is intentionally a synchronous context-manager factory so it wraps
# both sync and async stages uniformly (``with self._trace.stage(...):``) and
# is trivially provable in isolation.
# ---------------------------------------------------------------------------

# Canonical gateway pipeline stage names, so a tracer plugin and the wrapper
# agree on span names without a hard import between them.
GATEWAY_TRACE_STAGES = (
    "inbound",
    "admit",
    "agent.run",
    "llm.call",
    "tool.call",
    "outbox.enqueue",
    "delivery",
)


@runtime_checkable
class GatewayTraceHook(Protocol):
    """Structural contract for tracing a gateway pipeline stage as a span.

    A hook is fired around each stage of the inbound -> agent -> tool ->
    delivery pipeline. Implementations return a context manager whose scope is
    the span: entering starts it, exiting ends it, and an exception propagating
    out marks the span as failed. The default core implementation
    (:class:`NullGatewayTraceHook`) is a no-op so tracing is zero-cost when no
    exporter is attached.

    The contract is deliberately dependency-free: no OpenTelemetry import lives
    in core. A ``praisonai-plugins`` exporter implements ``stage`` with
    ``tracer.start_as_current_span(...)`` and carries the correlation id as a
    span attribute. Example::

        with self._trace.stage(
            "agent.run",
            correlation_id=current_correlation_id(),
            session=sid,
        ):
            reply = await agent.astart(text)
    """

    def stage(
        self,
        name: str,
        *,
        correlation_id: "Optional[str]" = None,
        **attrs: Any,
    ) -> "AbstractContextManager[Any]":
        """Open a tracing scope for pipeline stage ``name``.

        Args:
            name: The stage name (see :data:`GATEWAY_TRACE_STAGES`), used as the
                span name.
            correlation_id: The inbound turn's correlation id, attached as a
                span attribute so spans and logs share a key.
            **attrs: Extra span attributes (e.g. ``session``, ``model``,
                ``tool``, ``channel``).

        Returns:
            A context manager delimiting the span's lifetime.
        """
        ...


class NullGatewayTraceHook:
    """Zero-cost no-op :class:`GatewayTraceHook` used when tracing is disabled.

    Every stage call returns a lightweight, argument-ignoring null context
    manager (one small allocation per call), so firing the seam adds negligible
    overhead on the hot path. This is the default a gateway uses until an
    exporter plugin (e.g. the OTel/OTLP plugin in ``praisonai-plugins``) is
    supplied.
    """

    @staticmethod
    @contextmanager
    def _null_scope() -> "Iterator[None]":
        yield None

    def stage(
        self,
        name: str,
        *,
        correlation_id: "Optional[str]" = None,
        **attrs: Any,
    ) -> "AbstractContextManager[Any]":
        """Return a no-op context manager, ignoring all arguments."""
        return self._null_scope()


# Shared singleton: the default no-op hook is stateless, so one instance is
# reused everywhere a gateway needs a zero-cost default.
NULL_GATEWAY_TRACE_HOOK = NullGatewayTraceHook()


def resolve_trace_hook(
    hook: "Optional[GatewayTraceHook]",
) -> "GatewayTraceHook":
    """Return ``hook`` when a tracer is supplied, else the no-op default.

    A tiny helper so a gateway can accept an optional ``tracer=`` argument and
    always hold a callable hook without branching on ``None`` at every stage.

    Args:
        hook: A user/plugin-supplied trace hook, or ``None``.

    Returns:
        ``hook`` if not ``None``, otherwise the shared
        :data:`NULL_GATEWAY_TRACE_HOOK`.
    """
    return hook if hook is not None else NULL_GATEWAY_TRACE_HOOK


# ---------------------------------------------------------------------------
# Gateway self-lifecycle command guardrail (Issue #2753)
#
# A running gateway is a long-lived process that hosts an agent which can act on
# the same host — it can call a shell tool or author a scheduled job. Nothing
# inspects the *content* of an agent-issued command to stop it from targeting
# the gateway's own lifecycle: ``praisonai gateway stop``, ``pkill -f
# 'praisonai gateway'``, or ``systemctl --user stop`` the gateway unit would
# take the process itself down (self-DoS), and under an external supervisor can
# become a respawn flap. Approval gating does not help — it decides *whether*
# an agent may run a tool, not *whether a specific command is self-destructive*.
#
# This is the pure, import-free decision seam for a default-deny lifecycle
# guardrail, symmetric with the other gateway policy protocols above
# (``SendPolicy``, ``ScaleToZeroPolicy``, ``DrainMarkerPolicy``, …). The wrapper
# consults it *before* a shell/CLI tool executes and *before* a scheduled job
# is registered; a denied command returns a clean, model-readable reason rather
# than running. Matching is command-anchored (structural token inspection, not
# prose) so ordinary English mentioning "stop the gateway" is never tripped,
# and it scans the command string (and any resolved script text). It is
# on-by-default and opt-outable via ``enabled=False``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleCommandDecision:
    """Closed decision shape for a self-lifecycle command evaluation.

    Attributes:
        allow: Whether the command may run (``True``) or is refused
            (``False``) because it targets this gateway's own lifecycle.
        reason: Model-readable explanation, populated on denial so the caller
            can surface *why* the command was blocked.
        matched: The specific command fragment that triggered the deny (for
            logging / the blocked-attempt audit line); empty when allowed.
    """

    allow: bool
    reason: str = ""
    matched: str = ""


@runtime_checkable
class LifecycleCommandPolicyProtocol(Protocol):
    """Protocol for guarding an agent from stopping its own gateway.

    Pure, import-free decision contract consulted by the wrapper *before* a
    shell/CLI tool executes and *before* a scheduled job is registered. The
    wrapper supplies the resolved command string (and, when a script file is
    involved, its text); the policy returns a :class:`LifecycleCommandDecision`
    that either allows the command or refuses it because its effect is to
    stop / restart / reload / kill *this* gateway process. Concrete pattern
    sets are swappable (a plugin may supply a richer one); this contract keeps
    the *decision* testable in isolation, symmetric with
    :class:`SendPolicyProtocol` / :class:`GatewayConcurrencyPolicyProtocol`.

    A config-driven default (:class:`LifecycleCommandGuardPolicy`) is provided
    for the common ``praisonai gateway stop`` / ``pkill … gateway`` /
    ``systemctl stop <unit>`` case.
    """

    def evaluate(
        self,
        command: str,
        *,
        agent_id: str = "",
    ) -> LifecycleCommandDecision:
        """Return a :class:`LifecycleCommandDecision` for ``command``."""
        ...


class LifecycleCommandGuardPolicy:
    """Config-driven, command-anchored guard against gateway self-lifecycle hits.

    The default referenced by ``gateway.lifecycle_guard`` blocks in
    ``gateway.yaml`` and the ``BotOS(..., lifecycle_policy=...)`` Python
    surface. It is intentionally minimal and dependency-free so the decision
    lives in core and is provable in isolation; the wrapper owns the consult
    points (shell-tool executor, scheduler job registration) and the audit log.

    Matching is *structural*, not prose-based, to avoid false positives on
    ordinary English (e.g. "please stop the gateway from spamming"):

    * ``praisonai gateway stop|restart|reload`` — the CLI self-control verbs,
      matched only when ``praisonai`` and ``gateway`` appear as adjacent
      command tokens followed by a lifecycle verb.
    * ``pkill`` / ``kill`` / ``killall`` naming the gateway (a configured
      ``process_names`` token — ``praisonai`` by default — appearing as a whole
      component in the argument list or a ``-f`` pattern).
    * ``systemctl`` / ``launchctl`` / ``sc`` ``stop`` / ``restart`` / ``kill``
      on a unit whose name mentions the gateway (same whole-component match).

    Matching is *whole-component*, not bare substring: unrelated services whose
    name merely contains a token (``api-gateway``, ``kong-gateway``) are not
    tripped, while the real ``praisonai-gateway`` unit still matches.

    The scan is applied to every ``;``/``&&``/``||``/pipe-separated segment of
    the command *and* to any additional script text supplied, so a command that
    shells out to a wrapper script cannot smuggle the intent past the guard.

    ``default_allow`` is a fail posture: on any internal parsing error the guard
    keeps today's behaviour (allow) unless ``default_allow=False`` is set for a
    strict, fail-closed deployment. ``enabled=False`` disables the guard
    entirely (an operator who legitimately wants an agent to manage the
    process).

    Example::

        LifecycleCommandGuardPolicy()                    # on by default
        LifecycleCommandGuardPolicy(enabled=False)       # opt out
        LifecycleCommandGuardPolicy(process_names=["praisonai", "mybot"])
    """

    _CLI_VERBS = frozenset({"stop", "restart", "reload", "kill", "down"})
    _SERVICE_MGRS = frozenset({"systemctl", "launchctl", "service", "sc"})
    _SERVICE_VERBS = frozenset(
        {"stop", "restart", "reload", "kill", "disable", "down"}
    )
    _KILL_CMDS = frozenset({"pkill", "kill", "killall"})
    _SEGMENT_SPLIT = ("&&", "||", "|", ";", "\n")

    def __init__(
        self,
        enabled: bool = True,
        process_names: Optional[List[str]] = None,
        default_allow: bool = True,
    ):
        self.enabled = bool(enabled)
        # Default to the project's own, *specific* identity token. Bare
        # ``"gateway"`` is deliberately NOT a default deny token — it is too
        # generic and would false-positive on unrelated services whose name
        # contains it (``api-gateway``, ``kong-gateway``). The CLI-form rule
        # (``praisonai gateway stop``) still catches the self-control verbs via
        # the adjacent ``gateway`` sub-command, which needs no per-name entry.
        names = process_names if process_names else ["praisonai"]
        # Lower-cased, de-duplicated identity tokens that name *this* gateway.
        self.process_names = [str(n).strip().lower() for n in names if str(n).strip()]
        self.default_allow = bool(default_allow)

    def _mentions_self(self, text: str) -> bool:
        """Whether ``text`` names this gateway process/unit.

        Uses *whole-component* matching, not bare substring containment, so an
        unrelated service whose name merely *contains* a configured token is
        not tripped. The text is split into identifier components on whitespace
        and the ``- _ . / : @``, ``'`` / ``"`` characters that delimit service
        units, paths and quoted ``-f`` patterns; a configured name matches only
        when it equals one of those components. Thus the default
        ``process_names=["praisonai"]`` matches ``praisonai-gateway`` (real
        unit) and ``pkill -f praisonai`` but NOT ``api-gateway`` /
        ``kong-gateway`` / ``my-praisonaibot``.
        """
        import re

        components = {c for c in re.split(r"[\s\-_./:@'\"]+", text) if c}
        return any(name in components for name in self.process_names)

    @staticmethod
    def _tokenize(segment: str) -> List[str]:
        """Best-effort shell tokenization; falls back to whitespace split."""
        import shlex

        try:
            return shlex.split(segment)
        except ValueError:
            return segment.split()

    def _segment_targets_self(self, segment: str) -> str:
        """Return the offending fragment if ``segment`` hits our lifecycle.

        Returns an empty string when the segment is benign.
        """
        lowered = segment.lower()
        tokens = [t.lower() for t in self._tokenize(segment)]
        if not tokens:
            return ""
        # Drop common leading privilege/env prefixes so the real command verb
        # (e.g. ``sudo praisonai gateway stop``) is inspected structurally.
        idx = 0
        while idx < len(tokens) and tokens[idx] in ("sudo", "env", "nohup", "exec"):
            idx += 1
        head = tokens[idx:]
        if not head:
            return ""

        cmd = head[0]
        # Normalise a path-qualified executable (``/usr/bin/pkill``) to its base.
        base = cmd.rsplit("/", 1)[-1]

        # 1) <cli> gateway <verb> — the CLI self-control form. Enforce the
        #    documented adjacency (``praisonai gateway stop``) rather than a
        #    loose "words appear somewhere" match, and honour ``process_names``
        #    so a renamed/forked CLI (``mybot gateway stop`` with
        #    ``process_names=["mybot"]``) is covered symmetrically with rules 2/3.
        cli_names = set(self.process_names) | {"praisonai"}
        for gi, token in enumerate(head):
            if token != "gateway":
                continue
            prev_is_cli = gi >= 1 and head[gi - 1] in cli_names
            next_is_verb = gi + 1 < len(head) and head[gi + 1] in self._CLI_VERBS
            if prev_is_cli and next_is_verb:
                return segment.strip()

        # 2) kill / pkill / killall naming the gateway
        if base in self._KILL_CMDS:
            args = head[1:]
            # -f/-fl pattern match, or an explicit process-name argument.
            if self._mentions_self(" ".join(args)):
                return segment.strip()

        # 3) service manager stop/restart on our unit
        if base in self._SERVICE_MGRS:
            args = head[1:]
            if any(v in self._SERVICE_VERBS for v in args) and self._mentions_self(
                lowered
            ):
                return segment.strip()

        return ""

    def evaluate(
        self,
        command: str,
        *,
        agent_id: str = "",
    ) -> LifecycleCommandDecision:
        """Return a :class:`LifecycleCommandDecision` for ``command``.

        Args:
            command: The resolved command / scheduled-job command string (may
                also carry appended script text — every segment is scanned).
            agent_id: Optional agent identity (accepted for parity with the
                other policy protocols; unused by the default guard).

        Returns:
            An *allow* decision when the command is benign, or a *deny*
            decision naming the offending fragment when it would stop / restart
            / kill this gateway.
        """
        if not self.enabled:
            return LifecycleCommandDecision(allow=True)
        if not isinstance(command, str) or not command.strip():
            return LifecycleCommandDecision(allow=True)

        try:
            segments: List[str] = [command]
            for sep in self._SEGMENT_SPLIT:
                expanded: List[str] = []
                for seg in segments:
                    expanded.extend(seg.split(sep))
                segments = expanded

            for seg in segments:
                offending = self._segment_targets_self(seg)
                if offending:
                    return LifecycleCommandDecision(
                        allow=False,
                        reason=(
                            "Refusing: command would stop/restart/kill this "
                            "gateway process (self-lifecycle guard)"
                        ),
                        matched=offending,
                    )
        except Exception:
            # Parsing must never crash the caller: honour the configured fail
            # posture (fail-open by default, fail-closed when default_allow is
            # False for a strict, hosted gateway).
            if not self.default_allow:
                return LifecycleCommandDecision(
                    allow=False,
                    reason=(
                        "Refusing: could not prove command is safe for this "
                        "gateway (self-lifecycle guard, fail-closed)"
                    ),
                    matched=command.strip(),
                )
            return LifecycleCommandDecision(allow=True)

        return LifecycleCommandDecision(allow=True)


# Backward-compatible alias following the repo's ``*Protocol`` convention.
LifecycleCommandPolicy = LifecycleCommandPolicyProtocol


# ---------------------------------------------------------------------------
# Application-level connection liveness (Issue #2798)
#
# The gateway advertises a ``heartbeat_ms`` policy and stamps every session's
# ``last_activity``, but nothing enforces it: there is no protocol-level
# ping/pong frame and no server-side sweep, so a *half-open* connection (peer
# vanished, no FIN/RST — routine behind NAT/proxies/load-balancers/mobile) can
# linger forever, keeping presence "online" and silently queuing/dropping
# messages routed to it.
#
# This closes the loop with one transport-agnostic contract: a ``PING``/``PONG``
# event pair (see :class:`EventType`) plus a pure, import-free
# :class:`LivenessPolicy` — symmetric with the other gateway policy protocols
# above (``SendPolicy``, ``DrainTimeoutPolicy``, ``ConcurrencyLimitPolicy``, …).
# The policy owns only the *decision* (``KEEP`` vs ``REAP``) over a stamped
# ``last_activity`` and a ``now`` timestamp; the wrapper server owns the
# heartbeat-emit + reaper task and the reference client owns the heartbeat-send
# + silence watchdog, each consuming this decision. A ``REAP`` maps onto
# :attr:`GatewayCloseCode.LIVENESS_TIMEOUT`.
# ---------------------------------------------------------------------------


class LivenessDecision(str, Enum):
    """Outcome of a connection-liveness evaluation.

    * ``KEEP`` — the connection has shown activity recently enough; leave it.
    * ``REAP`` — the connection missed too many heartbeats and is presumed
      dead/half-open; the server should close it with
      :attr:`GatewayCloseCode.LIVENESS_TIMEOUT` and release its
      session/presence/queue state.
    """

    KEEP = "keep"
    REAP = "reap"


@runtime_checkable
class LivenessPolicyProtocol(Protocol):
    """Protocol for application-level connection-liveness decisions.

    Pure, import-free decision contract consumed by the wrapper's gateway
    (heartbeat-emit + reaper task) and the reference client (heartbeat-send +
    silence watchdog). The caller supplies the connection's last-activity
    timestamp and the current time; the policy returns a
    :class:`LivenessDecision`. Concrete transport machinery (sending the
    ``PING`` frame, closing the socket, forcing a reconnect) lives in the
    implementations, since it needs the running event loop and live sockets;
    this contract keeps the *decision* testable in isolation, symmetric with
    :class:`GatewayDrainPolicyProtocol` / :class:`RateLimitPolicyProtocol`.

    A config-driven default (:class:`LivenessPolicy`) is provided for the
    common "heartbeat every ``interval_ms``, reap after N missed beats" case.
    """

    interval_ms: int
    missed_beats_before_reap: int

    def evaluate(self, last_activity: float, now: float) -> LivenessDecision:
        """Return a :class:`LivenessDecision` for the supplied timestamps."""
        ...


@dataclass(frozen=True)
class LivenessPolicy:
    """Config-driven, pure liveness policy for half-open connection reaping.

    The default referenced by ``gateway.liveness`` blocks in ``gateway.yaml``
    and the ``WebSocketGateway(..., liveness_policy=...)`` Python surface. It is
    intentionally minimal and dependency-free so the decision lives in core and
    is provable in isolation; the wrapper owns the side effects (emit the
    ``PING`` heartbeat, close the socket, force the client reconnect).

    A connection is reaped once its ``last_activity`` is older than
    ``interval_ms × missed_beats_before_reap`` — i.e. it has silently missed
    that many heartbeat intervals. Any activity (an inbound frame, an inbound
    ``PONG``, or the peer's own ``PING``) refreshes ``last_activity`` and keeps
    the connection alive. The reference client typically force-reconnects after
    ``~2×`` the interval of silence, so it heals before the server reaps it.

    The window derivation is shared with the client watchdog via
    :meth:`reap_deadline` / :attr:`interval_seconds` so both sides agree on the
    same arithmetic from one advertised ``interval_ms``.

    ``interval_ms`` of ``0`` disables liveness reaping entirely (today's
    behaviour: ``last_activity`` is stamped but never acted upon), so the
    feature is fully backward-compatible and opt-in.

    Example::

        LivenessPolicy(interval_ms=30_000, missed_beats_before_reap=2)
    """

    interval_ms: int = 30_000
    missed_beats_before_reap: int = 2

    def __post_init__(self) -> None:
        if self.interval_ms < 0:
            raise ValueError(
                f"interval_ms must be >= 0 (use 0 to disable liveness reaping), "
                f"got {self.interval_ms!r}"
            )
        if self.missed_beats_before_reap < 1:
            raise ValueError(
                f"missed_beats_before_reap must be >= 1, "
                f"got {self.missed_beats_before_reap!r}"
            )

    @property
    def enabled(self) -> bool:
        """Whether liveness reaping is active (a positive interval is set)."""
        return self.interval_ms > 0

    @property
    def interval_seconds(self) -> float:
        """The heartbeat interval expressed in seconds."""
        return self.interval_ms / 1000.0

    def reap_deadline(self, last_activity: float) -> float:
        """Return the absolute time after which the connection is stale.

        A connection is reaped when the evaluation-time ``now`` is strictly
        above this deadline (``now > reap_deadline(last_activity)``). Exposed
        so the server reaper and the client watchdog derive the same window
        from one advertised interval.
        """
        return last_activity + self.interval_seconds * self.missed_beats_before_reap

    def evaluate(self, last_activity: float, now: float) -> LivenessDecision:
        """Return :attr:`LivenessDecision.REAP` iff the connection is stale.

        Args:
            last_activity: The connection's last-activity timestamp (same clock
                as ``now`` — the wrapper uses a monotonic clock).
            now: The current timestamp.

        Returns:
            :attr:`LivenessDecision.KEEP` while reaping is disabled or the
            connection is within its liveness window; otherwise
            :attr:`LivenessDecision.REAP`.
        """
        if not self.enabled:
            return LivenessDecision.KEEP
        if now > self.reap_deadline(last_activity):
            return LivenessDecision.REAP
        return LivenessDecision.KEEP
