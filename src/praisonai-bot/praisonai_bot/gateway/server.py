"""
WebSocket Gateway Server for PraisonAI.

Provides a WebSocket-based gateway for multi-agent coordination,
session management, and real-time communication.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import secrets
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

from praisonaiagents.gateway import (
    GatewayConfig,
    GatewayEvent,
    GatewayMessage,
    EventType,
    OperatorScope,
    PROTOCOL_VERSION,
    MIN_PROTOCOL_VERSION,
    MAX_PROTOCOL_VERSION,
)
from praisonaiagents.gateway.protocols import (
    ConnectErrorCode,
    ConnectRecoveryStep,
    GatewayCloseCode,
    HelloResult,
    HelloError,
    GATEWAY_PROTOCOL_VERSION,
    MIN_CLIENT_PROTOCOL_VERSION,
    ReloadStatus,
    compute_config_revision,
)
from praisonaiagents.session.protocols import SessionStoreProtocol
from praisonaiagents.session.store import DefaultSessionStore

logger = logging.getLogger(__name__)

from .unicode_utils import safe_error_message, safe_log_message, extract_root_cause_from_error
from .supervisor import ChannelSupervisor


# WebSocket close code for a slow-consumer eviction. 1013 ("Try Again Later")
# is the closest standard code for a server that is shedding a client it cannot
# keep up with; the structured GatewayCloseCode.SLOW_CONSUMER reason travels in
# the close ``reason`` so clients can branch deterministically.
SLOW_CONSUMER_CLOSE_CODE = 1013

# WebSocket close code used when a session is force-closed because the shared
# gateway secret it authenticated under was rotated/revoked. 4001 is in the
# private-use (4000–4999) range reserved for application-defined codes; the
# structured GatewayCloseCode.CREDENTIALS_ROTATED reason travels in the close
# ``reason`` so clients can branch deterministically and re-authenticate.
CREDENTIALS_ROTATED_CLOSE_CODE = 4001


class _ChannelBotOS:
    """Minimal ``BotOS``-shaped view over the gateway's channel bots.

    Issue #2624: the gateway owns a flat ``{channel_name: bot}`` registry
    rather than a :class:`~praisonai.bots.botos.BotOS`, but the resilient
    :class:`~praisonai.bots.delivery.DeliveryRouter` only needs ``get_bot`` /
    ``list_bots``. This thin adapter exposes exactly that surface — with the
    same case-insensitive lookup the gateway's own ``_deliver_*`` paths used —
    so the scheduled/hook delivery path can reuse the router unchanged.
    """

    def __init__(self, channel_bots: Dict[str, Any]) -> None:
        self._channel_bots = channel_bots

    def list_bots(self) -> List[str]:
        return list(self._channel_bots.keys())

    def get_bot(self, platform: str) -> Optional[Any]:
        bot = self._channel_bots.get(platform)
        if bot is not None:
            return bot
        # Case-insensitive fallback mirrors the gateway's prior lookup so a
        # configured "Telegram" resolves a "telegram" target and vice versa.
        for name, candidate in self._channel_bots.items():
            if name.lower() == platform.lower():
                return candidate
        return None


def _delivery_text_digest(text: str) -> str:
    """Short, stable digest of a delivery body for idempotency keys.

    Issue #2624: the scheduler/hook delivery callbacks receive only the target
    and text (not the job id), so a crash-and-resume that re-fires the *same*
    result to the *same* target produces the same key and is deduplicated by
    the router's bounded LRU, preventing a double-post. A genuinely different
    result (different text) yields a different key and is delivered.
    """
    import hashlib

    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def _should_bypass_loopback_auth(
    bind_host: Optional[str],
    client_host: Optional[str],
    request_headers,
    *,
    allow_env: Optional[str] = None,
) -> bool:
    """Decide whether a request qualifies for the loopback dev auth bypass.

    Permissive by default when the gateway is bound to a loopback interface
    (``127.0.0.1``/``localhost``/``::1``), matching the "loopback permissive,
    external strict" design intent (#1506): a fresh ``python app.py`` on
    localhost should serve the dashboard and APIs in the browser without
    copying a token. Externally bound gateways (``0.0.0.0``, LAN IPs) stay
    strict and always require auth.

    The bypass additionally requires the request to originate from localhost
    with no proxy headers present, so a proxied/forwarded request can never
    inherit loopback trust.

    ``ALLOW_LOOPBACK_BYPASS`` (passed via ``allow_env``) is an explicit
    override:
      - ``true``/``1``/``yes`` force-enables the bypass regardless of bind host
      - ``false``/``0``/``no`` force-disables it even on a loopback bind

    Args:
        bind_host: Interface the gateway is bound to.
        client_host: Remote address of the incoming request.
        request_headers: Mapping-like request headers (supports ``in``).
        allow_env: Value of ``ALLOW_LOOPBACK_BYPASS`` (defaults to the env var).
    """
    from .origin_check import is_loopback

    if allow_env is None:
        allow_env = os.environ.get("ALLOW_LOOPBACK_BYPASS", "")
    allow_env = (allow_env or "").strip().lower()

    if allow_env in ("false", "0", "no"):
        return False
    if allow_env not in ("true", "1", "yes"):
        # Not explicitly set: default to permissive only when the gateway
        # itself is bound to a loopback interface.
        if not is_loopback(bind_host or ""):
            return False

    # The client must itself be a loopback peer. Use ``is_loopback`` (not an
    # exact-string match) so semantically-loopback addresses such as
    # ``127.0.0.2``, ``127.255.255.255`` or the expanded IPv6 form
    # ``0:0:0:0:0:0:0:1`` are accepted too — otherwise a fresh local request
    # from one of those peers would wrongly get a 401 (Greptile #2945).
    if not is_loopback(client_host or ""):
        return False
    # Reject if proxy headers are present (indicates request went through proxy)
    proxy_headers = ["x-forwarded-for", "via", "x-real-ip", "x-forwarded-host"]
    return not any(header in request_headers for header in proxy_headers)


class _ClientConn:
    """Per-connection outbound delivery with a bounded buffer.

    Each connected client gets its own bounded send queue drained by a
    dedicated task. This isolates the shared broadcast path so one slow,
    stalled, or half-open consumer cannot apply backpressure to (head-of-line
    block) delivery to healthy clients, and bounds how much can accumulate for
    any single client.

    ``offer`` is non-blocking: it admits a frame only if doing so keeps the
    client within both the queued-frame and buffered-byte ceilings. When a
    frame cannot be admitted the client is a genuine slow consumer and the
    caller evicts it with a typed ``SLOW_CONSUMER`` reason.

    Backwards compatibility: when ``max_buffered_bytes <= 0`` and
    ``max_queued_frames <= 0`` the bounds are disabled and ``offer`` always
    admits, preserving best-effort delivery.
    """

    __slots__ = (
        "ws",
        "client_id",
        "max_buffered_bytes",
        "max_queued_frames",
        "_queue",
        "buffered_bytes",
        "_task",
        "_closed",
    )

    def __init__(
        self,
        ws: Any,
        client_id: str,
        max_buffered_bytes: int,
        max_queued_frames: int,
    ) -> None:
        self.ws = ws
        self.client_id = client_id
        self.max_buffered_bytes = max(0, int(max_buffered_bytes))
        self.max_queued_frames = max(0, int(max_queued_frames))
        # Unbounded asyncio.Queue; the ceilings are enforced in ``offer`` so we
        # never block the producer (the shared broadcast loop).
        self._queue: asyncio.Queue = asyncio.Queue()
        self.buffered_bytes = 0
        self._task: Optional[asyncio.Task] = None
        self._closed = False

    @staticmethod
    def _frame_size(data: Any) -> int:
        """Approximate the wire size of a frame for byte accounting."""
        try:
            import json

            return len(json.dumps(data, default=str).encode("utf-8"))
        except Exception:
            return 0

    def start(self) -> None:
        """Start the background drain task for this connection."""
        if self._task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Sync client registration (e.g. unit tests) — no running loop yet.
            # The drain task is started lazily on the first ``offer`` once the
            # gateway event loop is running, so no frames are lost.
            return
        self._task = loop.create_task(self._drain())

    def offer(self, data: Any) -> bool:
        """Try to enqueue a frame within the configured bounds.

        Returns ``True`` if the frame was admitted, ``False`` if admitting it
        would exceed a ceiling (the caller should evict this slow consumer).
        """
        if self._closed:
            return False
        # Lazily start the drain task. When a client is registered from a
        # synchronous context (e.g. ``add_client`` before the event loop is
        # running) ``start()`` cannot schedule the drain and leaves ``_task``
        # as ``None``. ``offer`` always runs on the event loop in production,
        # so starting here guarantees queued frames are drained rather than
        # accumulating silently until the client is spuriously evicted.
        if self._task is None:
            self.start()
        size = self._frame_size(data)
        if self.max_queued_frames > 0 and self._queue.qsize() >= self.max_queued_frames:
            return False
        if self.max_buffered_bytes > 0 and (
            size > self.max_buffered_bytes
            or (
                self.buffered_bytes + size > self.max_buffered_bytes
                and self._queue.qsize() > 0
            )
        ):
            # Allow at least one in-flight frame so a single payload that fits
            # within the byte ceiling is never spuriously rejected, but reject a
            # single frame that already exceeds the ceiling on its own.
            return False
        self._queue.put_nowait((data, size))
        self.buffered_bytes += size
        return True

    async def _drain(self) -> None:
        """Drain queued frames to the websocket one at a time."""
        try:
            while True:
                data, size = await self._queue.get()
                if data is None:  # sentinel: stop draining
                    self._queue.task_done()
                    break
                try:
                    await self.ws.send_json(data)
                except Exception as e:
                    logger.error(
                        f"Send error to client {self.client_id}: {e}"
                    )
                    # The transport is broken; mark closed so subsequent
                    # ``offer`` calls are rejected instead of silently
                    # enqueueing frames into a queue with no live consumer.
                    self._closed = True
                    self._queue.task_done()
                    break
                finally:
                    self.buffered_bytes = max(0, self.buffered_bytes - size)
                self._queue.task_done()
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            raise

    async def close(self) -> None:
        """Stop the drain task and release accounting state."""
        if self._closed:
            return
        self._closed = True
        try:
            self._queue.put_nowait((None, 0))
        except Exception:
            pass
        task = self._task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
            except Exception:
                task.cancel()
        self.buffered_bytes = 0


@dataclass
class GatewaySession:
    """A gateway session tracking a conversation between client and agent."""
    
    _session_id: str
    _agent_id: str
    _client_id: Optional[str] = None
    _is_active: bool = True
    _created_at: float = field(default_factory=time.time)
    _last_activity: float = field(default_factory=time.time)
    _state: Dict[str, Any] = field(default_factory=dict)
    _messages: List[GatewayMessage] = field(default_factory=list)
    _max_messages: int = 1000
    _event_cursor: int = 0  # Monotonic cursor for event replay
    _events: List[GatewayEvent] = field(default_factory=list)  # Event history for replay
    _was_resumed: bool = False  # Track if session was resumed from persistence
    _sequence: int = 0  # Monotonic sequence number for gap detection
    _protocol_version: int = PROTOCOL_VERSION  # Negotiated protocol version
    _capabilities: List[str] = field(default_factory=list)  # Client-advertised capability tokens
    
    # Stepper & Concurrency logic
    _inbox: asyncio.Queue = field(default_factory=asyncio.Queue)
    _is_executing: bool = False
    
    @property
    def session_id(self) -> str:
        return self._session_id
    
    @property
    def agent_id(self) -> Optional[str]:
        return self._agent_id
    
    @property
    def client_id(self) -> Optional[str]:
        return self._client_id
    
    @property
    def is_active(self) -> bool:
        return self._is_active
    
    @property
    def created_at(self) -> float:
        return self._created_at
    
    @property
    def last_activity(self) -> float:
        return self._last_activity
    
    @property
    def protocol_version(self) -> int:
        """The protocol version negotiated during the handshake."""
        return self._protocol_version
    
    @property
    def capabilities(self) -> List[str]:
        """Capability tokens advertised by the client during the handshake."""
        return list(self._capabilities)
    
    def get_state(self) -> Dict[str, Any]:
        return dict(self._state)
    
    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value
        self._last_activity = time.time()
    
    def add_message(self, message: GatewayMessage) -> None:
        self._messages.append(message)
        self._last_activity = time.time()
        if self._max_messages > 0 and len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]
    
    def get_messages(self, limit: Optional[int] = None) -> List[GatewayMessage]:
        if limit:
            return list(self._messages[-limit:])
        return list(self._messages)
    
    def close(self) -> None:
        self._is_active = False
    
    def add_event(self, event: GatewayEvent) -> int:
        """Add an event and return its cursor position."""
        self._event_cursor += 1
        self._sequence += 1
        event.data['cursor'] = self._event_cursor
        event.sequence = self._sequence  # Add sequence for gap detection
        self._events.append(event)
        self._last_activity = time.time()
        # Keep events bounded to prevent unbounded growth
        if len(self._events) > self._max_messages * 2:
            self._events = self._events[-self._max_messages:]
        return self._event_cursor
    
    def get_oldest_cursor(self) -> int:
        """Get the oldest event cursor still retained in the buffer.
        
        When the buffer is empty, returns the current cursor position,
        which correctly indicates that any cursor < _event_cursor would
        require resync (since no events are retained).
        """
        if self._events:
            return self._events[0].data.get('cursor', self._event_cursor)
        return self._event_cursor
    
    def get_events_since(self, cursor: int) -> List[GatewayEvent]:
        """Get events since the given cursor."""
        return [e for e in self._events if e.data.get('cursor', 0) > cursor]
    
    def check_resync_required(self, since_cursor: Optional[int]) -> bool:
        """Check if resync is required based on the requested cursor."""
        if since_cursor is None:
            return False
        oldest_cursor = self.get_oldest_cursor()
        return since_cursor < oldest_cursor
    
    def get_snapshot(self) -> Dict[str, Any]:
        """Get a snapshot of the current session state for resync."""
        return {
            "session_id": self._session_id,
            "agent_id": self._agent_id,
            "state": dict(self._state),
            "messages": [{
                "content": msg.content,
                "sender_id": msg.sender_id,
                "session_id": msg.session_id,
                "message_id": msg.message_id,
                "timestamp": msg.timestamp,
                "metadata": msg.metadata,
            } for msg in self._messages],
            "event_cursor": self._event_cursor,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary for persistence."""
        # Drain inbox queue to a list for serialization
        pending_inbox = []
        temp_items = []
        while not self._inbox.empty():
            try:
                item = self._inbox.get_nowait()
                temp_items.append(item)
                pending_inbox.append(item)
            except asyncio.QueueEmpty:
                break
        
        # Put items back into the queue to preserve order
        for item in temp_items:
            self._inbox.put_nowait(item)
        
        return {
            "session_id": self._session_id,
            "agent_id": self._agent_id,
            "client_id": self._client_id,
            "is_active": self._is_active,
            "created_at": self._created_at,
            "last_activity": self._last_activity,
            "state": self._state,
            "messages": [{
                "content": msg.content,
                "sender_id": msg.sender_id,
                "session_id": msg.session_id,
                "message_id": msg.message_id,
                "timestamp": msg.timestamp,
                "metadata": msg.metadata,
            } for msg in self._messages],
            "event_cursor": self._event_cursor,
            "sequence": self._sequence,
            "protocol_version": self._protocol_version,
            "capabilities": list(self._capabilities),
            "events": [e.to_dict() for e in self._events[-100:]],  # Keep last 100 events
            "pending_inbox": pending_inbox,
            "is_executing": self._is_executing,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], max_messages: int = 1000) -> 'GatewaySession':
        """Deserialize session from dictionary."""
        session = cls(
            _session_id=data["session_id"],
            _agent_id=data["agent_id"],
            _client_id=data.get("client_id"),
            _is_active=data.get("is_active", True),
            _created_at=data.get("created_at", time.time()),
            _last_activity=data.get("last_activity", time.time()),
            _state=data.get("state", {}),
            _max_messages=max_messages,
        )
        
        # Mark this session as resumed from persistence
        session._was_resumed = True
        
        # Restore messages
        for msg_data in data.get("messages", []):
            msg = GatewayMessage(
                content=msg_data["content"],
                sender_id=msg_data["sender_id"],
                session_id=msg_data["session_id"],
                message_id=msg_data.get("message_id"),
                timestamp=msg_data.get("timestamp", time.time()),
                metadata=msg_data.get("metadata", {}),
            )
            session._messages.append(msg)
        
        # Restore event cursor and events
        session._event_cursor = data.get("event_cursor", 0)
        session._sequence = data.get("sequence", session._event_cursor)
        session._protocol_version = data.get("protocol_version", PROTOCOL_VERSION)
        restored_caps = data.get("capabilities", [])
        session._capabilities = list(restored_caps) if isinstance(restored_caps, list) else []
        for event_data in data.get("events", []):
            event = GatewayEvent.from_dict(event_data)
            session._events.append(event)
        
        # Restore pending inbox messages
        for message in data.get("pending_inbox", []):
            session._inbox.put_nowait(message)
        
        # Restore execution state
        session._is_executing = data.get("is_executing", False)
        
        return session

    async def queue_message(self, message: str) -> None:
        """Queue a user message for execution after the current operation."""
        await self._inbox.put(message)
        
    def get_next_message(self) -> Optional[str]:
        """Fetch the next queued message if available without blocking."""
        if self._inbox.empty():
            return None
        return self._inbox.get_nowait()
        
    def mark_executing(self, status: bool) -> None:
        """Mark the session as currently executing an agent workflow."""
        self._is_executing = status


class ReloadAction(Enum):
    """Actions that can be taken during config reload."""
    NONE = "none"  # No action needed
    HOT = "hot"  # Apply in-place without restart
    RESTART_AGENTS = "restart_agents"  # Recreate agents only
    RESTART_CHANNEL = "restart_channel"  # Restart specific channel
    FULL_RESTART = "full_restart"  # Full stop/start all channels


@dataclass
class ReloadPlan:
    """Plan for selective config reload actions."""
    restart_channels: Set[str] = field(default_factory=set)
    reload_agents: bool = False
    hot_reload_paths: Set[str] = field(default_factory=set)
    full_restart: bool = False
    
    def add_channel_restart(self, channel_name: str) -> None:
        """Mark a channel for restart."""
        if not self.full_restart:
            self.restart_channels.add(channel_name)
    
    def requires_full_restart(self) -> None:
        """Mark that a full restart is required."""
        self.full_restart = True
        self.restart_channels.clear()  # No need for selective restarts


class WebSocketGateway:
    """WebSocket gateway server for multi-agent coordination.
    
    Implements the GatewayProtocol for WebSocket-based communication.
    
    Example:
        from praisonai_bot.gateway import WebSocketGateway
        from praisonaiagents import Agent
        
        # Create gateway
        gateway = WebSocketGateway(port=8765)
        
        # Register agents
        agent = Agent(name="assistant")
        gateway.register_agent(agent)
        
        # Start gateway
        await gateway.start()
    """
    
    @classmethod
    def from_config_file(
        cls,
        config_path: str = "config.yaml",
        section: str = "gateway",
    ) -> "WebSocketGateway":
        """Create a gateway from a YAML configuration file.
        
        Gap S5: Enables gateway config persistence via standard config files.
        
        Args:
            config_path: Path to the YAML config file
            section: Config section containing gateway settings (default: "gateway")
            
        Returns:
            Configured WebSocketGateway instance
            
        Example config.yaml:
            gateway:
              host: "0.0.0.0"
              port: 8765
              auth_token: "${GATEWAY_AUTH_TOKEN}"
              max_connections: 1000
              heartbeat_interval: 30
        """
        import yaml
        
        if not os.path.exists(config_path):
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return cls()
        
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        
        gateway_config = raw.get(section, {})
        if not gateway_config:
            logger.warning(f"No '{section}' section in {config_path}, using defaults")
            return cls()
        
        # Substitute environment variables
        def _substitute(value):
            if isinstance(value, str):
                return cls._substitute_env_vars(value)
            return value
        
        # Build GatewayConfig with session configuration
        from praisonaiagents.gateway.config import SessionConfig
        
        # Parse session configuration if present
        session_config = SessionConfig()
        if "session" in gateway_config:
            session_data = gateway_config["session"]
            session_config = SessionConfig(
                timeout=int(session_data.get("timeout", 3600)),
                max_messages=int(session_data.get("max_messages", 1000)),
                persist=bool(session_data.get("persist", False)),
                persist_path=_substitute(session_data.get("persist_path")),
                resume_window=int(session_data.get("resume_window", 86400)),
            )
        
        config = GatewayConfig(
            host=_substitute(gateway_config.get("host", "127.0.0.1")),
            port=int(gateway_config.get("port", 8765)),
            auth_token=_substitute(gateway_config.get("auth_token")),
            allowed_origins=gateway_config.get("allowed_origins", []),
            max_connections=int(gateway_config.get("max_connections", 1000)),
            heartbeat_interval=int(gateway_config.get("heartbeat_interval", 30)),
            reconnect_timeout=int(gateway_config.get("reconnect_timeout", 60)),
            ssl_cert=_substitute(gateway_config.get("ssl_cert")),
            ssl_key=_substitute(gateway_config.get("ssl_key")),
            max_buffered_bytes=int(
                gateway_config.get("max_buffered_bytes", 1024 * 1024)
            ),
            max_queued_frames=int(
                gateway_config.get("max_queued_frames", 1000)
            ),
            max_concurrent_runs=int(
                gateway_config.get("max_concurrent_runs", 0) or 0
            ),
            queue_depth=int(gateway_config.get("queue_depth", 0) or 0),
            overflow_policy=str(
                gateway_config.get("overflow_policy", "reject") or "reject"
            ),
            preauth_max_connections_per_ip=int(
                gateway_config.get("preauth_max_connections_per_ip", 32)
            ),
            max_unauthorized_frames=int(
                gateway_config.get("max_unauthorized_frames", 10)
            ),
            session_config=session_config,
        )
        
        logger.info(f"Gateway config loaded from {config_path}")
        return cls(config=config)
    
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        config: Optional[GatewayConfig] = None,
        session_store: Optional[SessionStoreProtocol] = None,
        openai_api: Optional[bool] = None,
        mcp: Optional[bool] = None,
        identity_resolver: Optional[Any] = None,
    ):
        """Initialize the gateway.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            config: Optional gateway configuration
            session_store: Optional session store for persistence
            openai_api: Serve OpenAI-compatible endpoints
                (``/v1/chat/completions``, ``/v1/responses``, ``/v1/models``)
                backed by this gateway's live agents/sessions. Overrides
                ``config.api.openai`` when set.
            mcp: Serve an MCP JSON-RPC endpoint (``/mcp``) exposing this
                gateway's agents as tools. Overrides ``config.api.mcp`` when set.
            identity_resolver: Optional cross-platform identity resolver
                (Issue #3020). When supplied it is stamped onto every channel
                bot's session manager so a paired/linked user keeps one
                continuous session + memory across channels. A constructor
                value wins over the declarative ``identity:`` block in
                ``gateway.yaml``. ``None`` preserves today's per-platform keys.
        """
        self.config = config or GatewayConfig(host=host, port=port)

        # Issue #3020: shared cross-platform identity resolver. Mirrors BotOS —
        # stamped onto each channel bot's session manager in ``start_channels``
        # / ``_start_single_channel`` so continuity works in the flagship
        # gateway process, not only the in-process BotOS orchestrator.
        self._identity_resolver = identity_resolver
        # A constructor-supplied resolver is *explicit* and always wins: the
        # declarative ``identity:`` block (and its hot-reload reconciliation)
        # never clobbers it. CLI ``--identity-store`` sets this flag too.
        self._identity_resolver_explicit = identity_resolver is not None
        # Normalized (enabled, store) signature of the ``identity:`` block that
        # produced the current YAML-built resolver, so hot-reload can tell an
        # unchanged block from an enable/disable/re-point.
        self._identity_resolver_signature: Optional[Tuple[Any, ...]] = None

        # Explicit constructor toggles win over any config-provided defaults so
        # ``WebSocketGateway(openai_api=True, mcp=True)`` works without a config.
        if openai_api is not None:
            self.config.api.openai = bool(openai_api)
        if mcp is not None:
            self.config.api.mcp = bool(mcp)
        
        # Set bind_host for bind-aware authentication
        self.config.bind_host = self.config.host
        
        if hasattr(self.config, 'auth_token') and not self.config.auth_token:
            # Prefer a user-configured token (persisted by `praisonai onboard`
            # to ~/.praisonai/.env as GATEWAY_AUTH_TOKEN) so the dashboard
            # URL stays stable across daemon restarts. Only fall back to
            # generating a random ephemeral token if nothing is set.
            env_tok = os.environ.get("GATEWAY_AUTH_TOKEN", "").strip()
            if env_tok:
                self.config.auth_token = env_tok
                logger.info("Gateway using GATEWAY_AUTH_TOKEN from environment")
            else:
                import secrets
                from praisonaiagents.gateway.protocols import is_loopback
                from .auth import get_auth_token_fingerprint, save_auth_token_to_env

                if is_loopback(self.config.bind_host):
                    self.config.auth_token = secrets.token_hex(16)
                    fingerprint = get_auth_token_fingerprint(self.config.auth_token)
                    logger.warning(
                        f"No auth_token provided for Gateway server. Generated temporary token: {fingerprint}. "
                        "For production, set GATEWAY_AUTH_TOKEN."
                    )

                    # Save to ~/.praisonai/.env for future use
                    try:
                        save_auth_token_to_env(self.config.auth_token)
                    except Exception as e:
                        logger.debug(f"Could not save auth token to .env: {e}")
        
        # Ensure single source of truth: export resolved token so all auth paths use the same secret
        if self.config.auth_token:
            os.environ["GATEWAY_AUTH_TOKEN"] = self.config.auth_token
        
        # Load allowed origins from environment if not set
        if hasattr(self.config, 'allowed_origins') and not self.config.allowed_origins:
            env_origins = os.environ.get("GATEWAY_ALLOWED_ORIGINS", "").strip()
            if env_origins:
                # Split by comma and clean up whitespace
                self.config.allowed_origins = [origin.strip() for origin in env_origins.split(",") if origin.strip()]
                logger.info(f"Gateway using GATEWAY_ALLOWED_ORIGINS from environment: {self.config.allowed_origins}")
        
        self._host = self.config.host
        self._port = self.config.port
        
        self._is_running = False
        self._draining = False
        self._started_at: Optional[float] = None
        self._server = None
        
        self._agents: Dict[str, "Agent"] = {}
        self._sessions: Dict[str, GatewaySession] = {}
        self._clients: Dict[str, Any] = {}  # WebSocket connections
        self._client_conns: Dict[str, _ClientConn] = {}  # client_id -> bounded outbound conn
        self._client_sessions: Dict[str, str] = {}  # client_id -> session_id
        self._client_scopes: Dict[str, List[str]] = {}  # client_id -> operator scopes
        # Issue #2661: fingerprint of the shared secret each authenticated
        # client connected under, so rotating ``auth_token`` can force-close
        # every session stamped with a stale secret (instant credential
        # revocation) instead of leaving it trusted for its whole lifetime.
        self._client_auth_generation: Dict[str, str] = {}  # client_id -> auth generation
        
        # Initialize session store based on configuration
        if session_store:
            self._session_store: Optional[SessionStoreProtocol] = session_store
        elif self.config.session_config.persist:
            # Use DefaultSessionStore when persistence is enabled
            persist_path = self.config.session_config.persist_path
            self._session_store = DefaultSessionStore(session_dir=persist_path)
            logger.info(f"Session persistence enabled, using directory: {persist_path or '~/.praisonai/sessions/'}")
        else:
            self._session_store = None
            logger.info("Session persistence disabled, using in-memory sessions only")
        
        # Track session TTLs for cleanup
        self._session_ttls: Dict[str, float] = {}  # session_id -> expiry timestamp
        
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        
        # Multi-bot lifecycle
        self._channel_bots: Dict[str, Any] = {}  # channel_name -> bot instance
        # Issue #2624: resilient outbound delivery for the gateway's own
        # scheduled/hook path. Lazily built (see ``delivery_router``) so the
        # scheduled-job and hook replies share the same token-bucket rate
        # limiting, LRU idempotency dedup, and dead-target suppression the
        # interactive BotOS path already uses, instead of a bare send.
        self._delivery_router: Optional[Any] = None
        self._dead_targets: Optional[Any] = None
        self._routing_rules: Dict[str, Dict[str, str]] = {}  # channel_name -> {context -> agent_id}
        self._routing_bindings: Dict[str, List[Any]] = {}  # channel_name -> [RouteBinding] (Issue #2225)
        self._channel_tasks: Dict[str, asyncio.Task] = {}  # channel_name -> asyncio task
        
        # Pairing store for channel authorization
        from .pairing import PairingStore
        self.pairing_store = PairingStore()
        
        # Scheduler tick background task
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Store last loaded config for diff-driven reload
        self._loaded_config: Optional[Dict[str, Any]] = None

        # Issue #2533: bounded drain window applied when a hot-reload restarts
        # a channel, so in-flight turns on that channel finish before it is
        # bounced. Populated from gateway.yaml / CLI in ``start_with_config``.
        # ``None``/0 preserves the prior immediate-restart behaviour.
        self._reload_drain_timeout: Optional[float] = None
        # Issue #2533: serialize reloads. The file watcher, SIGHUP handler, and
        # concurrent SIGHUPs all funnel through ``reload_config``; without a
        # lock two reloads can interleave across drain/stop/start awaits and
        # clobber ``_loaded_config`` / channel state. This lock guarantees one
        # reload finishes before the next begins. Created lazily on the running
        # loop so it binds to the correct loop (Issue #2533).
        self._reload_lock: Optional[asyncio.Lock] = None
        # Background config-watch task handle (event-driven or polling).
        self._config_watch_task: Optional[asyncio.Task] = None

        # Issue #3049: config hot-reload observability. Record the outcome of
        # the last reload attempt and the revision of the config actually
        # running, so ``health()`` can surface "did my edit take effect / is
        # the watcher still alive?" instead of swallowing it into a log line.
        # ``_reload_watcher_active`` flips to False only when the watcher
        # genuinely gives up, so silent degradation is detectable.
        self._reload_status: Optional["ReloadStatus"] = None
        self._applied_config_revision: Optional[str] = None
        self._config_path: Optional[str] = None
        self._reload_watcher_active: bool = False
        
        # Session cleanup background task
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # PID lock for single-instance enforcement
        self._pid_lock: Optional[Any] = None
        
        # Channel supervisor for resilient bot management
        self._channel_supervisor = ChannelSupervisor()
        self._health_config = None  # Will be set from config if provided

        # Message-flow metrics surface (served at GET /metrics). Lazily built so
        # the gateway carries no metrics overhead when the module is unused.
        try:
            from ..bots._metrics import GatewayMetrics
            self._metrics = GatewayMetrics()
        except Exception:  # pragma: no cover — defensive, keep gateway usable
            self._metrics = None

        # Inbound trigger hooks (Issue #2281): declarative POST /hooks/<path>
        # surfaces that start an agent run from an external event. Routes are
        # mounted dynamically when the server starts.
        self._hooks: Dict[str, Any] = {}  # path -> HookConfig
        # Bounded idempotency store: dedup key -> insertion time (seconds).
        self._hook_idempotency: "OrderedDict[str, float]" = OrderedDict()
        self._hook_idempotency_max = 10_000
        self._hook_idempotency_ttl = 86_400.0  # 24h
        # Keys currently being processed. Used to deduplicate *concurrent*
        # identical deliveries: the idempotency store is only written after a
        # run succeeds, so without this set two simultaneous requests would both
        # pass the seen-check across the ``await`` and run the agent twice.
        self._hook_inflight: set = set()

        # Issue #3021: opt-in gateway lifecycle — idle/scale-to-zero, epoch-aware
        # external drain marker, and a crash-loop restart guard. These reuse the
        # pure core policies (``ScaleToZeroPolicy``/``DrainMarkerPolicy``/
        # ``RestartLoopGuard``) so the primary gateway runtime gets the same
        # guarantees ``BotOS`` already has. All default to off/None so an
        # always-on gateway pays zero cost and behaviour stays backward-compatible.
        self._idle_policy: Optional[Any] = None
        self._drain_marker_policy: Optional[Any] = None
        self._drain_marker_path: Optional[str] = None
        self._restart_loop_guard: Optional[Any] = None
        self._instantiation_epoch: Optional[str] = None
        self._last_handled_drain_epoch: Optional[str] = None
        self._is_dormant: bool = False
        self._last_inbound_ts: float = time.time()
        self._on_quiesce: Optional[Callable[[], Any]] = None
        self._lifecycle_task: Optional[asyncio.Task] = None
        self._drain_marker_task: Optional[asyncio.Task] = None

    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def port(self) -> int:
        return self._port
    
    @property
    def host(self) -> str:
        return self._host
    
    async def start(self) -> None:
        """Start the gateway server."""
        if self._is_running:
            logger.warning("Gateway already running")
            return
        
        # Preflight port collision check
        from .port_utils import check_port_available, GatewayPIDLock, format_collision_error
        
        pid_lock = GatewayPIDLock(host=self._host, port=self._port)
        
        # Check if port is available
        port_available, pid_using_port = check_port_available(self._host, self._port)
        if not port_available:
            # Check if we have a PID lock
            lock_info = pid_lock.get_lock_info()
            error_msg = format_collision_error(self._host, self._port, lock_info)
            logger.error("Gateway startup failed due to port collision")
            raise RuntimeError(error_msg)
        
        # Try to acquire PID lock
        if not pid_lock.acquire_lock(self._host, self._port):
            lock_info = pid_lock.get_lock_info()
            error_msg = format_collision_error(self._host, self._port, lock_info)
            logger.error("Gateway startup failed - another instance is running")
            raise RuntimeError(error_msg)
        
        # Store PID lock for cleanup
        self._pid_lock = pid_lock
        
        # Validate bind-aware auth configuration before starting
        from .auth import assert_external_bind_safe
        self.config.host = self._host
        self.config.port = self._port
        self.config.bind_host = self._host
        assert_external_bind_safe(self.config)

        # Import origin checking functionality
        from .origin_check import check_origin, is_loopback, GatewayStartupError

        # Validate allowed_origins configuration for external binds
        if not is_loopback(self._host) and not self.config.allowed_origins:
            logger.error("Gateway startup failed due to configuration error")
            raise GatewayStartupError(
                f"Gateway is binding to external interface '{self._host}' but no allowed_origins configured. "
                "Set GATEWAY_ALLOWED_ORIGINS environment variable or configure allowed_origins in gateway config. "
                "Example: GATEWAY_ALLOWED_ORIGINS=\"https://your-ui.example.com,https://localhost:3000\""
            )
        
        try:
            from starlette.applications import Starlette
            from starlette.routing import Route, WebSocketRoute
            from starlette.responses import JSONResponse
            from starlette.websockets import WebSocket, WebSocketDisconnect
            import uvicorn
        except ImportError:
            raise ImportError(
                "Gateway requires starlette and uvicorn. "
                "Install with: pip install praisonai[api]"
            )
        
        async def health(request):
            return JSONResponse(self.health())
        
        def _loopback_bypass_active(request) -> bool:
            """Whether the development loopback auth bypass applies to ``request``.

            Permissive by default when the gateway is bound to a loopback
            interface (``127.0.0.1``/``localhost``/``::1``), matching the
            "loopback permissive, external strict" design intent (#1506): a
            fresh ``python app.py`` on localhost should serve the dashboard and
            APIs in the browser without copying a token. Externally bound
            gateways (``0.0.0.0``, LAN IPs) stay strict and always require auth.

            The bypass additionally requires the request to originate from
            localhost with no proxy headers present, so a proxied/forwarded
            request can never inherit loopback trust.

            ``ALLOW_LOOPBACK_BYPASS`` still acts as an explicit override:
              - ``true``/``1``/``yes`` force-enables the bypass (legacy behaviour)
              - ``false``/``0``/``no`` force-disables it even on a loopback bind
                (opt-in strict auth for local development)

            Used by both ``_check_auth`` (auth bypass) and scope resolution so
            the two stay consistent — a loopback request that bypasses auth is
            also granted all operator scopes.
            """
            bind_host = getattr(self.config, "bind_host", None) or self.config.host
            client_host = getattr(request.client, 'host', None) if request.client else None
            return _should_bypass_loopback_auth(bind_host, client_host, request.headers)

        async def ready(request):
            """GET /ready — readiness probe for load balancers / orchestrators.

            Returns HTTP 200 only when the gateway is fully started and not
            draining. Returns 503 during startup and graceful shutdown so a
            load balancer stops routing new connections before drain begins.
            """
            failing = await self._readiness_failures()
            uptime = time.time() - self._started_at if self._started_at else 0
            return JSONResponse(
                {"ready": not failing, "failing": failing, "uptime": uptime},
                status_code=200 if not failing else 503,
            )
        
        async def live(request):
            """GET /live — liveness probe.

            Returns HTTP 200 as long as the process and its event loop are
            responsive, independent of transient channel health, so
            orchestrators don't needlessly restart on a recoverable blip.
            """
            ok = await self._event_loop_responsive()
            return JSONResponse(
                {"alive": ok}, status_code=200 if ok else 503,
            )

        async def metrics(request):
            """GET /metrics — message-flow metrics in Prometheus text format.

            Exposes inbound/dispatched/duplicate/outbound counters plus live
            gauges (outbox depth, approval pending, active sessions) so a live
            bot fleet can be monitored without grepping logs. Returns 404 when
            the metrics surface is unavailable.

            Protected by the same token check as other operational endpoints
            (e.g. ``/info``) so channel names and message-flow volumes are not
            exposed to unauthenticated clients on externally bound gateways.
            """
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            self._refresh_metric_gauges()
            if self._metrics is None:
                return JSONResponse({"error": "metrics unavailable"}, status_code=404)
            from starlette.responses import PlainTextResponse
            return PlainTextResponse(
                self._metrics.render_prometheus(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )
        
        def _check_auth(request) -> Optional[JSONResponse]:
            """Validate auth token if configured. Returns error response or None.

            Accepts either:
              - ``Authorization: Bearer <token>`` header (preferred for APIs)
              - ``?token=<token>`` query parameter (so the dashboard URL from
                ``praisonai onboard`` is clickable in a browser)
              - Cookie-based authentication (praisonai_session cookie)
            """
            if not self.config.auth_token:
                return None
            
            # Check for cookie authentication first
            try:
                from .cookie_auth import create_auth_manager_from_env
                auth_manager = create_auth_manager_from_env()
                if auth_manager:
                    cookie_header = request.headers.get("cookie", "")
                    token_from_cookie = auth_manager.extract_token_from_cookies(cookie_header)
                    if token_from_cookie and auth_manager.is_token_valid(token_from_cookie):
                        return None  # Authenticated via cookie
            except ImportError:
                pass
            
            # Check loopback bypass for local requests (only if explicitly enabled)
            if _loopback_bypass_active(request):
                # Allow local requests without auth for development
                return None
            
            # Fall back to token-based auth
            auth_header = request.headers.get("authorization", "")
            token: str = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            else:
                token = request.query_params.get("token", "")
                if token:
                    import warnings
                    warnings.warn(
                        "DeprecationWarning: Use Sec-WebSocket-Protocol or magic link cookie",
                        DeprecationWarning,
                        stacklevel=2
                    )
            
            if not token:
                return JSONResponse(
                    {"error": "Authentication required. Please use your magic link."},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not secrets.compare_digest(token, self.config.auth_token):
                return JSONResponse(
                    {"error": "Invalid authentication token"},
                    status_code=403,
                )
            return None

        def _extract_request_token(request) -> Optional[str]:
            """Best-effort extraction of the operator token from a request.

            Used only to resolve operator *scopes* when a scope policy is
            configured — authentication itself is handled by ``_check_auth``.
            Prefers the cookie session token, then bearer header, then the
            legacy ``?token=`` query parameter.
            """
            try:
                from .cookie_auth import create_auth_manager_from_env
                auth_manager = create_auth_manager_from_env()
                if auth_manager:
                    cookie_header = request.headers.get("cookie", "")
                    tok = auth_manager.extract_token_from_cookies(cookie_header)
                    if tok and auth_manager.is_token_valid(tok):
                        return tok
            except ImportError:
                pass

            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header[7:]
            return request.query_params.get("token") or None

        def _resolve_operator_scopes(request) -> List[str]:
            """Resolve the operator scopes for an HTTP request.

            Backward compatible: when no scope policy is configured the client
            is granted all scopes (identical to today's binary auth). When the
            development loopback bypass applies the client is likewise granted
            all scopes, matching the auth-bypass intent.
            """
            if not self.config.has_scope_policy:
                return [s.value for s in OperatorScope.all()]
            if _loopback_bypass_active(request):
                return [s.value for s in OperatorScope.all()]
            return self.config.resolve_scopes(_extract_request_token(request))

        def _require_scope(request, scope: OperatorScope) -> Optional[JSONResponse]:
            """Return a 403 response if the request lacks ``scope``, else None."""
            scopes = _resolve_operator_scopes(request)
            if OperatorScope.ADMIN.value in scopes or scope.value in scopes:
                return None
            return JSONResponse(
                {"error": "insufficient scope", "required_scope": scope.value},
                status_code=403,
            )

        async def info(request):
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            api_cfg = getattr(self.config, "api", None)
            return JSONResponse({
                "name": "PraisonAI Gateway",
                "version": "1.0.0",
                "agents": list(self._agents.keys()),
                "sessions": len(self._sessions),
                "clients": len(self._clients),
                "api": api_cfg.to_dict() if api_cfg is not None else {},
            })
        
        async def _reject_connection(
            websocket: WebSocket,
            *,
            close_code: int,
            error: HelloError,
        ) -> None:
            """Reject a connection with a structured ``hello_error`` envelope.

            Accepts the socket so an application-level frame carrying the
            machine-readable ``(code, next_step, retry_after_seconds)`` recovery
            envelope can be delivered, then closes with the transport code.
            Best-effort: if the frame cannot be sent we still close the socket.
            """
            try:
                await websocket.accept()
                await websocket.send_json(error.to_dict())
            except Exception as exc:
                logger.debug(
                    f"Could not deliver hello_error envelope ({error.code.value}): {exc}"
                )
            try:
                await websocket.close(code=close_code, reason=error.message)
            except Exception as exc:
                logger.debug(
                    f"Could not close rejected websocket ({error.code.value}): {exc}"
                )

        async def websocket_endpoint(websocket: WebSocket):
            # Get client IP for rate limiting
            client_ip = websocket.client.host if websocket.client else "unknown"

            # Rate limiting for WebSocket upgrades (exempt loopback per acceptance criteria)
            if not is_loopback(client_ip) and not is_loopback(self._host):
                if not _ws_upgrade_rate.allow("ws_upgrade", client_ip):
                    retry = _ws_upgrade_rate.time_until_allowed("ws_upgrade", client_ip)
                    await _reject_connection(
                        websocket,
                        close_code=4008,
                        error=HelloError(
                            code=ConnectErrorCode.RATE_LIMITED,
                            message="Too many connection attempts",
                            next_step=ConnectRecoveryStep.WAIT_THEN_RETRY,
                            retry_after_seconds=max(1, int(retry)) if retry else None,
                        ),
                    )
                    logger.warning(f"WebSocket upgrade rate limited for {client_ip} (retry in {retry:.0f}s)")
                    return

            # Pre-auth concurrent-connection budget (Issue #2620). Bound the
            # number of *unauthenticated* sockets one source IP may hold open at
            # once so a hostile client cannot park many half-open connections up
            # to max_connections. Loopback is exempt so local CLIs are never
            # locked out. The slot is released on auth-success or on close.
            _ip_is_loopback = is_loopback(client_ip) or is_loopback(self._host)
            _released = {"done": False}

            def _release_budget():
                # Release the pre-auth slot exactly once (on auth-success or
                # close), so an authenticated connection no longer counts
                # against the unauthenticated budget.
                if not _released["done"] and not _ip_is_loopback:
                    _released["done"] = True
                    _preauth_budget.release(client_ip)

            if not _ip_is_loopback:
                if not _preauth_budget.acquire(client_ip):
                    await _reject_connection(
                        websocket,
                        close_code=4029,
                        error=HelloError(
                            code=ConnectErrorCode.RATE_LIMITED,
                            message="Too many unauthenticated connections",
                            next_step=ConnectRecoveryStep.WAIT_THEN_RETRY,
                        ),
                    )
                    logger.warning(
                        f"WebSocket pre-auth connection budget exhausted for {client_ip}"
                    )
                    return

            try:
                await _connect_ws(websocket, client_ip, _release_budget)
            finally:
                _release_budget()
            return

        async def _connect_ws(websocket, client_ip, _release_budget):
            # Origin validation (CSWSH defense)
            origin = websocket.headers.get("origin")
            try:
                if not check_origin(origin, self.config.allowed_origins, self._host):
                    await _reject_connection(
                        websocket,
                        close_code=4003,
                        error=HelloError(
                            code=ConnectErrorCode.ORIGIN_NOT_ALLOWED,
                            message="Origin not allowed",
                            next_step=ConnectRecoveryStep.DO_NOT_RETRY,
                        ),
                    )
                    logger.warning(f"WebSocket connection rejected: origin '{origin}' not in allowed list")
                    return
            except (GatewayStartupError, ValueError) as e:
                # check_origin() raises ValueError when an external bind has no
                # allowed_origins configured; route both through the structured
                # configuration_error envelope rather than the generic error path.
                await _reject_connection(
                    websocket,
                    close_code=4003,
                    error=HelloError(
                        code=ConnectErrorCode.CONFIGURATION_ERROR,
                        message="Configuration error",
                        next_step=ConnectRecoveryStep.DO_NOT_RETRY,
                    ),
                )
                logger.error(f"WebSocket connection failed due to configuration error: {e}")
                return

            # Authenticate WebSocket via session cookie or query param
            operator_token: Optional[str] = None
            if self.config.auth_token:
                authenticated = False
                
                # First try cookie-based authentication
                try:
                    from .cookie_auth import CookieAuthManager
                    auth_manager = CookieAuthManager(secret_key=self.config.auth_token)
                    cookie_header = websocket.headers.get("cookie", "")
                    token_from_cookie = auth_manager.extract_token_from_cookies(cookie_header)
                    if token_from_cookie and auth_manager.is_token_valid(token_from_cookie):
                        authenticated = True
                        operator_token = token_from_cookie
                except ImportError:
                    pass
                
                # Fall back to query param token authentication
                if not authenticated:
                    ws_token = websocket.query_params.get("token", "")
                    if ws_token and secrets.compare_digest(ws_token, self.config.auth_token):
                        authenticated = True
                        operator_token = ws_token
                
                if not authenticated:
                    await _reject_connection(
                        websocket,
                        close_code=4003,
                        error=HelloError(
                            code=ConnectErrorCode.AUTH_REQUIRED,
                            message="Authentication required",
                            next_step=ConnectRecoveryStep.REAUTHENTICATE,
                        ),
                    )
                    return
            
            await websocket.accept()
            # Auth succeeded: release the pre-auth budget slot so this now
            # authenticated connection no longer counts against the
            # unauthenticated per-IP budget.
            _release_budget()
            client_id = str(uuid.uuid4())
            self._clients[client_id] = websocket
            self._register_client_conn(client_id, websocket)
            # Resolve operator scopes for this connection (all scopes if no policy).
            self._client_scopes[client_id] = self.config.resolve_scopes(operator_token)
            # Issue #2661: stamp the session with the active secret's generation
            # so a later rotation can force-close it (instant revocation).
            self._client_auth_generation[client_id] = self._auth_generation()
            # Per-connection unauthorized-frame flood guard (Issue #2620).
            from .rate_limiter import UnauthorizedFloodGuard
            _flood_guard = UnauthorizedFloodGuard(
                max_unauthorized=getattr(
                    self.config, "max_unauthorized_frames", 10
                ),
            )
            
            logger.info(f"Client connected: {client_id}")
            
            await self.emit(GatewayEvent(
                type=EventType.CONNECT,
                data={"client_id": client_id},
                source=client_id,
            ))
            
            try:
                while True:
                    data = await websocket.receive_json()
                    unauthorized = await self._handle_client_message(client_id, data)
                    if unauthorized:
                        _should_close = _flood_guard.note_unauthorized()
                        if _flood_guard.should_log():
                            logger.warning(
                                "Unauthorized frame from client %s (%d total, "
                                "%d suppressed)",
                                client_id,
                                _flood_guard.count,
                                _flood_guard.suppressed,
                            )
                        if _should_close:
                            logger.warning(
                                "Closing client %s: unauthorized-frame flood "
                                "(%d frames)",
                                client_id,
                                _flood_guard.count,
                            )
                            await websocket.close(code=4028)
                            break
            except WebSocketDisconnect:
                logger.info(f"Client disconnected: {client_id}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self._clients.pop(client_id, None)
                await self._teardown_client_conn(client_id)
                self._client_scopes.pop(client_id, None)
                self._client_auth_generation.pop(client_id, None)
                session_id = self._client_sessions.pop(client_id, None)
                if session_id:
                    self.close_session(session_id)
                
                await self.emit(GatewayEvent(
                    type=EventType.DISCONNECT,
                    data={"client_id": client_id},
                    source=client_id,
                ))
        
        # ── Approval endpoints ─────────────────────────────────────────
        # Lazy-import approval machinery so it doesn't slow down startup
        # or fail if optional deps are missing.
        from .exec_approval import Resolution, get_exec_approval_manager
        from .rate_limiter import AuthRateLimiter
        from .pairing_routes import create_pairing_routes

        _approval_mgr = get_exec_approval_manager()
        # Rehydrate any pending approvals persisted by a previous process so a
        # restart doesn't silently drop in-flight human approvals. No-op when
        # the manager has no durable store configured.
        try:
            await _approval_mgr.rehydrate()
        except Exception:
            logger.exception("Failed to rehydrate pending gateway approvals")
        _approval_rate = AuthRateLimiter(max_attempts=10, window_seconds=60)
        _ws_upgrade_rate = AuthRateLimiter(max_attempts=10, window_seconds=60)
        # Issue #2620: pre-auth concurrent-connection budget per source IP.
        from .rate_limiter import PreauthConnectionBudget
        _preauth_budget = PreauthConnectionBudget(
            max_per_ip=getattr(
                self.config, "preauth_max_connections_per_ip", 32
            ),
        )

        # Create pairing routes
        _pairing_routes = create_pairing_routes(
            self.pairing_store,
            _check_auth,
            _approval_rate,
            scope_checker=lambda request: _require_scope(request, OperatorScope.PAIRING),
        )

        async def approval_pending(request):
            """GET /api/approval/pending — list pending approval requests."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err

            client_ip = request.client.host if request.client else "unknown"
            if not _approval_rate.allow("approval_pending", client_ip):
                retry = _approval_rate.time_until_allowed("approval_pending", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

            return JSONResponse({
                "pending": _approval_mgr.list_pending(),
                "allow_list": _approval_mgr.allowlist.list(),
            })

        async def approval_resolve(request):
            """POST /api/approval/resolve — approve or deny a tool request.

            Body: {"request_id": "...", "approved": true/false,
                   "reason": "...", "allow_always": false}
            """
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            scope_err = _require_scope(request, OperatorScope.APPROVALS)
            if scope_err:
                return scope_err

            client_ip = request.client.host if request.client else "unknown"
            if not _approval_rate.allow("approval_resolve", client_ip):
                retry = _approval_rate.time_until_allowed("approval_resolve", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            request_id = body.get("request_id", "")
            if not request_id:
                return JSONResponse(
                    {"error": "request_id is required"}, status_code=400,
                )

            resolution = Resolution(
                approved=bool(body.get("approved", False)),
                reason=str(body.get("reason", "")),
                allow_always=bool(body.get("allow_always", False)),
                scope_to_agent=bool(body.get("scope_to_agent", True)),
                scope_to_args=bool(body.get("scope_to_args", False)),
            )

            found = _approval_mgr.resolve(request_id, resolution)
            if not found:
                return JSONResponse(
                    {"error": "Request not found or already resolved"},
                    status_code=404,
                )

            return JSONResponse({
                "resolved": True,
                "request_id": request_id,
                "approved": resolution.approved,
            })

        async def approval_allowlist(request):
            """GET/POST/DELETE /api/approval/allow-list

            GET    → list allow-listed tools (and scoped grants)
            POST   → add a tool: {"tool_name": "...", "agent_id": "..."}
            DELETE → remove a tool: {"tool_name": "...", "agent_id": "..."}

            ``agent_id`` is optional. When omitted the grant applies to any
            agent (legacy behaviour); when provided the grant is scoped to that
            agent only. Grants are durable and survive gateway restarts.
            """
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err

            if request.method == "GET":
                resp = {"allow_list": _approval_mgr.allowlist.list()}
                list_scoped = getattr(
                    _approval_mgr.allowlist, "list_scoped", None
                )
                if callable(list_scoped):
                    try:
                        resp["grants"] = list_scoped()
                    except Exception:
                        logger.exception("Failed to list scoped approval grants")
                return JSONResponse(resp)

            # Mutating the approval allow-list is security-sensitive. Check the
            # scope *before* consuming the rate-limit budget so a read-only
            # client cannot drain a source IP's budget (which would otherwise
            # cause 429s on legitimate GETs from the same IP).
            scope_err = _require_scope(request, OperatorScope.APPROVALS)
            if scope_err:
                return scope_err

            client_ip = request.client.host if request.client else "unknown"
            if not _approval_rate.allow("approval_allowlist", client_ip):
                retry = _approval_rate.time_until_allowed("approval_allowlist", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )

            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            tool_name = body.get("tool_name", "")
            if not tool_name:
                return JSONResponse(
                    {"error": "tool_name is required"}, status_code=400,
                )

            agent_id = body.get("agent_id")
            if agent_id is not None:
                if not isinstance(agent_id, str) or not agent_id.strip():
                    return JSONResponse(
                        {"error": "agent_id must be a non-empty string"},
                        status_code=400,
                    )
                agent_id = agent_id.strip()

            if request.method == "POST":
                if agent_id and hasattr(_approval_mgr.allowlist, "add_scoped"):
                    _approval_mgr.allowlist.add_scoped(
                        agent_id=agent_id, tool_name=tool_name,
                        approver="gateway:operator",
                    )
                    return JSONResponse({"added": tool_name, "agent_id": agent_id})
                _approval_mgr.allowlist.add(tool_name)
                return JSONResponse({"added": tool_name})
            elif request.method == "DELETE":
                if agent_id and hasattr(_approval_mgr.allowlist, "revoke_scoped"):
                    removed = _approval_mgr.allowlist.revoke_scoped(
                        agent_id=agent_id, tool_name=tool_name,
                    )
                    if not removed:
                        return JSONResponse(
                            {"error": f"'{tool_name}' not granted for agent "
                                      f"'{agent_id}'"},
                            status_code=404,
                        )
                    return JSONResponse({"removed": tool_name, "agent_id": agent_id})
                removed = _approval_mgr.allowlist.remove(tool_name)
                if not removed:
                    return JSONResponse(
                        {"error": f"'{tool_name}' not in allow-list"},
                        status_code=404,
                    )
                return JSONResponse({"removed": tool_name})

            return JSONResponse({"error": "Method not allowed"}, status_code=405)

        # ── Magic Link Authentication ────────────────────────────────────
        from .magic_link import MagicLinkStore
        from .cookie_auth import create_auth_manager_from_env
        from .rate_limiter import AuthRateLimiter
        
        # Initialize magic link store and rate limiter
        _magic_store = MagicLinkStore()
        _magic_rate = AuthRateLimiter(max_attempts=5, window_seconds=60)
        
        async def magic_link_handler(request):
            """Handle GET /?link=<nonce> magic link authentication."""
            nonce = request.query_params.get("link", "")
            if not nonce:
                # No magic link, redirect to auth required page or return 401
                return JSONResponse(
                    {"error": "Authentication required. Get a fresh link: praisonai gateway mint-link"},
                    status_code=401
                )
            
            client_ip = request.client.host if request.client else "unknown"
            if not _magic_rate.allow("magic_link", client_ip):
                retry = _magic_rate.time_until_allowed("magic_link", client_ip)
                return JSONResponse(
                    {"error": "Rate limited", "retry_after_seconds": round(retry)},
                    status_code=429,
                )
            
            # Try to consume the nonce
            if not _magic_store.consume(nonce):
                return JSONResponse(
                    {"error": "This link was already used or has expired. Get a fresh one: praisonai gateway mint-link"},
                    status_code=401
                )
            
            # Create session cookie
            try:
                auth_manager = create_auth_manager_from_env()
                if not auth_manager:
                    return JSONResponse(
                        {"error": "Cookie authentication not available"},
                        status_code=500
                    )
                
                session_token = auth_manager.create_session(
                    user_id="gateway_user",
                    auth_method="magic_link"
                )
                
                # Determine if HTTPS
                is_https = (
                    request.headers.get("x-forwarded-proto") == "https" or
                    request.url.scheme == "https"
                )
                
                cookie_header = auth_manager.create_cookie_header(
                    session_token,
                    secure=is_https,
                    http_only=True,
                    same_site="Strict"
                )
                
                # Redirect to remove the nonce from URL
                from starlette.responses import RedirectResponse
                response = RedirectResponse(
                    url=str(request.url.replace(query="")),
                    status_code=302
                )
                response.headers["Set-Cookie"] = cookie_header
                return response
                
            except ImportError:
                return JSONResponse(
                    {"error": "Cookie authentication dependencies not available"},
                    status_code=500
                )
        
        # Channel control endpoints
        async def pause_channel_handler(request) -> JSONResponse:
            """POST /api/channels/{name}/pause — pause a channel."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            scope_err = _require_scope(request, OperatorScope.ADMIN)
            if scope_err:
                return scope_err
            channel_name = request.path_params["name"]
            success = self.pause_channel(channel_name)
            return JSONResponse({
                "success": success,
                "message": f"Channel '{channel_name}' {'paused' if success else 'could not be paused'}"
            })
        
        async def resume_channel_handler(request) -> JSONResponse:
            """POST /api/channels/{name}/resume — resume a paused channel."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            scope_err = _require_scope(request, OperatorScope.ADMIN)
            if scope_err:
                return scope_err
            channel_name = request.path_params["name"]
            success = self.resume_channel(channel_name)
            return JSONResponse({
                "success": success,
                "message": f"Channel '{channel_name}' {'resumed' if success else 'could not be resumed'}"
            })
        
        async def reconnect_channel_handler(request) -> JSONResponse:
            """POST /api/channels/{name}/reconnect — reconnect a channel."""
            auth_err = _check_auth(request)
            if auth_err:
                return auth_err
            scope_err = _require_scope(request, OperatorScope.ADMIN)
            if scope_err:
                return scope_err
            channel_name = request.path_params["name"]
            success = self.reconnect_channel(channel_name)
            return JSONResponse({
                "success": success,
                "message": f"Channel '{channel_name}' {'reconnected' if success else 'could not be reconnected'}"
            })
        
        def _check_hook_auth(request, hook) -> Optional[JSONResponse]:
            """Authenticate an inbound hook request.

            Prefers a hook-specific ``auth`` secret when configured; otherwise
            falls back to the gateway's standard auth (``_check_auth``). The
            secret is accepted only via ``Authorization: Bearer <token>`` and
            compared in constant time. A query-parameter token is deliberately
            not accepted: it would be written verbatim into the server's (and
            any reverse-proxy's) access logs, leaking the shared secret.
            """
            secret = getattr(hook, "auth", None)
            if not secret:
                return _check_auth(request)
            auth_header = request.headers.get("authorization", "")
            token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
            if not token:
                return JSONResponse(
                    {"error": "Authentication required"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not secrets.compare_digest(token, str(secret)):
                return JSONResponse(
                    {"error": "Invalid authentication token"}, status_code=403,
                )
            return None

        async def hook_handler(request) -> JSONResponse:
            """POST /hooks/{path} — generic inbound event trigger (Issue #2281).

            Authenticates, deduplicates, resolves a session, runs the agent (or
            wakes a session) and delivers the reply through a channel bot.
            """
            path = request.path_params.get("path", "")
            hook = self.get_hook(path)
            if hook is None or not getattr(hook, "enabled", True):
                return JSONResponse({"error": "hook not found"}, status_code=404)

            auth_err = _check_hook_auth(request, hook)
            if auth_err:
                return auth_err

            try:
                payload = await request.json()
            except ValueError:
                # Malformed JSON: reject rather than silently running on {} so a
                # bad request never triggers an agent with an unintended message.
                return JSONResponse(
                    {"error": "Invalid JSON. Send a JSON object payload."},
                    status_code=400,
                )
            if not isinstance(payload, dict):
                payload = {"value": payload}

            # Atomically reserve the idempotency key. ``_hook_reserve`` rejects
            # keys already recorded *or* currently in flight, so concurrent
            # identical deliveries are deduplicated even though recording is
            # deferred until after a successful run (which lets webhook senders
            # retry transient failures).
            idem = hook.resolve_idempotency_key(payload)
            if not self._hook_reserve(idem):
                return JSONResponse({"ok": True, "deduplicated": True})

            try:
                result = await self._run_hook(hook, payload)
            except Exception as e:  # noqa: BLE001
                self._hook_release(idem)
                logger.error("Hook '%s' execution error: %s", path, e)
                return JSONResponse(
                    {"ok": False, "error": str(e)}, status_code=500,
                )

            ok = result.get("ok", False)
            if ok:
                self._hook_record(idem)
            else:
                self._hook_release(idem)
            status = 200 if ok else 500
            return JSONResponse(result, status_code=status)

        routes = [
            Route("/", magic_link_handler, methods=["GET"]),
            Route("/hooks/{path:path}", hook_handler, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
            Route("/ready", ready, methods=["GET"]),
            Route("/live", live, methods=["GET"]),
            Route("/metrics", metrics, methods=["GET"]),
            Route("/info", info, methods=["GET"]),
            Route("/api/approval/pending", approval_pending, methods=["GET"]),
            Route("/api/approval/resolve", approval_resolve, methods=["POST"]),
            Route("/api/approval/allow-list", approval_allowlist, methods=["GET", "POST", "DELETE"]),
            Route("/api/pairing/pending", _pairing_routes["pending"], methods=["GET"]),
            Route("/api/pairing/approve", _pairing_routes["approve"], methods=["POST"]),
            Route("/api/pairing/revoke", _pairing_routes["revoke"], methods=["POST"]),
            Route("/api/channels/{name}/pause", pause_channel_handler, methods=["POST"]),
            Route("/api/channels/{name}/resume", resume_channel_handler, methods=["POST"]),
            Route("/api/channels/{name}/reconnect", reconnect_channel_handler, methods=["POST"]),
            WebSocketRoute("/ws", websocket_endpoint),
        ]

        # Issue #2715: additive, config-gated OpenAI-compatible / MCP protocol
        # surfaces on the SAME app and auth. Each request dispatches into the
        # gateway's own registered agents and shares its session store and
        # admission gate, so OpenAI-SDK/MCP clients reach the same stateful
        # agent as chat users. Disabled by default (config.api.*).
        api_cfg = getattr(self.config, "api", None)
        if api_cfg is not None and getattr(api_cfg, "enabled", False):
            from .api_endpoints import GatewayApiEndpoints
            self._api_endpoints = GatewayApiEndpoints(self)

            def _api_guarded(handler):
                async def _wrapped(request):
                    auth_err = _check_auth(request)
                    if auth_err:
                        return auth_err
                    return await handler(request)
                return _wrapped

            if api_cfg.openai:
                routes += [
                    Route(
                        "/v1/chat/completions",
                        _api_guarded(self._api_endpoints.openai_chat),
                        methods=["POST"],
                    ),
                    Route(
                        "/v1/responses",
                        _api_guarded(self._api_endpoints.openai_responses),
                        methods=["POST"],
                    ),
                    Route(
                        "/v1/models",
                        _api_guarded(self._api_endpoints.openai_models),
                        methods=["GET"],
                    ),
                ]
                logger.info("Gateway OpenAI-compatible API enabled (/v1/*)")
            if api_cfg.mcp:
                routes += [
                    Route(
                        "/mcp",
                        _api_guarded(self._api_endpoints.mcp_jsonrpc),
                        methods=["POST"],
                    ),
                ]
                logger.info("Gateway MCP endpoint enabled (/mcp)")

        app = Starlette(routes=routes)
        
        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        
        # Clear shutdown state so a stopped-then-restarted instance reports
        # ready again instead of being stuck reporting "draining".
        self._draining = False
        self._is_running = True
        self._started_at = time.time()
        
        # Start session cleanup task if persistence is enabled
        if self._session_store:
            await self._start_session_cleanup()
        
        logger.info(f"Gateway started on ws://{self._host}:{self._port}")
        
        try:
            await self._server.serve()
        except Exception as e:
            # Clean up PID lock on any startup failure
            if hasattr(self, '_pid_lock') and self._pid_lock:
                self._pid_lock.release_lock()
                self._pid_lock = None
            # Re-raise the original exception
            raise

    # ── Gateway lifecycle: idle/scale-to-zero + drain marker (Issue #3021) ──

    def _configure_lifecycle(self, lifecycle_cfg: Optional[Dict[str, Any]]) -> None:
        """Build opt-in lifecycle policies from a ``lifecycle:`` config block.

        Reuses the pure core policies rather than duplicating machinery:
        ``ScaleToZeroPolicy`` (idle-quiesce), ``DrainMarkerPolicy`` +
        ``current_epoch`` (epoch-aware external drain), and
        ``RestartLoopGuard`` (crash-loop breaker). Every sub-feature is off
        unless explicitly enabled, so always-on gateways are unchanged.

        Config shape (``gateway.yaml``)::

            lifecycle:
              scale_to_zero: { enabled: true, idle_minutes: 10, wake_url: "…" }
              drain:         { marker_path: "/data/gateway.drain" }
              restart_loop_guard: { max_restarts: 3, window_seconds: 60 }
        """
        if not isinstance(lifecycle_cfg, dict):
            return

        def _as_bool(v: Any, default: bool = False) -> bool:
            if isinstance(v, str):
                return v.strip().lower() in ("1", "true", "yes", "on")
            return bool(v) if v is not None else default

        # Scale-to-zero / idle dormancy.
        stz = lifecycle_cfg.get("scale_to_zero")
        if isinstance(stz, dict) and _as_bool(stz.get("enabled")):
            try:
                from praisonaiagents.gateway import ScaleToZeroPolicy

                idle_minutes = float(stz.get("idle_minutes", 10.0))
                self._idle_policy = ScaleToZeroPolicy(
                    idle_timeout_minutes=idle_minutes,
                    wake_url=stz.get("wake_url"),
                    enabled=True,
                )
                logger.info(
                    "Gateway scale-to-zero enabled (idle_minutes=%s)",
                    idle_minutes,
                )
            except (ImportError, ValueError) as e:
                logger.warning("Invalid scale_to_zero config; disabling: %s", e)
                self._idle_policy = None

        # Epoch-aware external drain marker.
        drain = lifecycle_cfg.get("drain")
        if isinstance(drain, dict) and drain.get("marker_path"):
            try:
                from praisonaiagents.gateway import (
                    DrainMarkerPolicy,
                    current_epoch,
                )

                self._drain_marker_policy = DrainMarkerPolicy()
                self._drain_marker_path = str(drain["marker_path"])
                self._instantiation_epoch = current_epoch()
                logger.info(
                    "Gateway drain-marker watch enabled (path=%s)",
                    self._drain_marker_path,
                )
            except ImportError as e:
                logger.warning("Drain-marker watch unavailable: %s", e)
                self._drain_marker_policy = None

        # Crash-loop restart guard.
        rlg = lifecycle_cfg.get("restart_loop_guard")
        if isinstance(rlg, dict) and _as_bool(rlg.get("enabled"), True):
            try:
                from praisonaiagents.gateway import RestartLoopGuard

                self._restart_loop_guard = RestartLoopGuard(
                    max_restarts=int(rlg.get("max_restarts", 3)),
                    window_seconds=float(rlg.get("window_seconds", 60.0)),
                )
            except (ImportError, ValueError) as e:
                logger.warning("Invalid restart_loop_guard config; disabling: %s", e)
                self._restart_loop_guard = None

    def _merge_lifecycle_overrides(
        self,
        lifecycle_cfg: Optional[Dict[str, Any]],
        drain_timeout_cfg: Optional[float],
    ) -> Optional[Dict[str, Any]]:
        """Fold CLI lifecycle overrides into the YAML ``lifecycle`` block.

        CLI flags stamped on the instance by the ``praisonai gateway`` command
        (``--scale-to-zero``, ``--idle-minutes``, ``--drain-marker``) win over
        the YAML so operators can toggle scale-to-zero without editing the
        file. Returns the (possibly newly created) merged block, or the
        original when there are no overrides.
        """
        stz_on = getattr(self, "_scale_to_zero_override", None)
        idle_min = getattr(self, "_idle_minutes_override", None)
        marker = getattr(self, "_drain_marker_override", None)
        if stz_on is None and idle_min is None and marker is None:
            return lifecycle_cfg

        merged: Dict[str, Any] = dict(lifecycle_cfg) if isinstance(lifecycle_cfg, dict) else {}
        if stz_on or idle_min is not None:
            stz = dict(merged.get("scale_to_zero") or {})
            if stz_on is not None:
                stz["enabled"] = bool(stz_on)
            if idle_min is not None:
                stz["idle_minutes"] = idle_min
            merged["scale_to_zero"] = stz
        if marker is not None:
            drain = dict(merged.get("drain") or {})
            drain["marker_path"] = marker
            merged["drain"] = drain
        return merged

    def notify_inbound(self) -> None:
        """Record inbound activity for idle tracking (cheap timestamp write).

        Safe to call always. When no idle policy is configured this is a
        no-op-cheap write; the idle loop also passively probes live session
        state, so live traffic is reflected even without explicit calls.
        """
        self._last_inbound_ts = time.time()

    def _probe_idle_facts(self) -> Tuple[int, float, bool]:
        """Read live liveness facts from gateway sessions for the idle policy.

        Returns ``(running_turns, last_inbound_ts, has_background_work)`` from
        the session state every code path already maintains (``_is_executing``,
        ``_last_activity``, pending inbox), merged with any explicitly recorded
        ``notify_inbound`` timestamp so both sources are honoured.
        """
        running = 0
        last_ts = self._last_inbound_ts
        has_pending = False
        for session in self._sessions.values():
            if getattr(session, "_is_executing", False):
                running += 1
            inbox = getattr(session, "_inbox", None)
            if inbox is not None and not inbox.empty():
                has_pending = True
            la = getattr(session, "_last_activity", None)
            if isinstance(la, (int, float)) and la > last_ts:
                last_ts = la
        return running, last_ts, has_pending

    async def wake(self) -> None:
        """Resume the gateway from dormancy. Idempotent (no-op when awake)."""
        if not self._is_dormant:
            return
        logger.info("Gateway waking from dormancy")
        self._is_dormant = False
        self.notify_inbound()

    async def _quiesce(self, reason: str) -> None:
        """Mark the gateway dormant and drive an optional host-suspend hook.

        The gateway keeps its listening socket (so an inbound request wakes it
        via ``notify_inbound``); the ``on_quiesce`` driver — when supplied —
        owns any deeper compute-host suspend (Fly/Modal/Daytona).
        """
        if self._is_dormant:
            return
        logger.info("Gateway quiescing (scale-to-zero): %s", reason)
        self._is_dormant = True
        if self._on_quiesce is not None:
            try:
                result = self._on_quiesce()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning("Gateway on_quiesce driver error: %s", e)

    async def _run_idle_loop(self) -> None:
        """Evaluate the idle policy and quiesce when the gateway is fully idle.

        Only scheduled when an ``idle_policy`` is configured. The decision is
        the pure core predicate; this loop supplies live facts and owns the
        side effects, mirroring ``BotOS._run_idle_loop``.
        """
        policy = self._idle_policy
        if policy is None:
            return
        wake_url = getattr(policy, "wake_url", None)
        if hasattr(policy, "should_arm"):
            if not policy.should_arm(
                transports_quiescable=True,
                wake_registered=wake_url is not None,
            ):
                logger.info(
                    "Gateway idle policy not armed (no wake path); staying always-on"
                )
                return
        logger.info("Gateway idle-dormancy armed (scale-to-zero)")
        try:
            while self._is_running:
                await asyncio.sleep(30)
                if self._is_dormant:
                    continue
                try:
                    running, last_ts, has_bg = self._probe_idle_facts()
                    decision = policy.is_idle(
                        running_turns=running,
                        last_inbound_ts=last_ts,
                        has_background_work=has_bg,
                        now=time.time(),
                    )
                except Exception as e:
                    logger.debug("Gateway idle evaluation error: %s", e)
                    continue
                if getattr(decision, "idle", False):
                    await self._quiesce(getattr(decision, "reason", ""))
        except asyncio.CancelledError:
            raise

    def _read_drain_marker(self) -> Optional[Dict[str, Any]]:
        """Read + parse the external drain marker file, or ``None`` if absent."""
        path = self._drain_marker_path
        if not path:
            return None
        try:
            import json

            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else None
        except (OSError, ValueError):
            return None

    async def _run_drain_marker_watch(self, drain_timeout: Optional[float]) -> None:
        """Poll for an epoch-matching external drain marker and act on it.

        A marker written by ``praisonai gateway drain`` triggers a bounded
        graceful drain. ``DrainMarkerPolicy`` ignores markers whose epoch does
        not match this instantiation, so a stale marker left on a durable
        volume by a machine restart never wedges a fresh process in "draining".
        """
        policy = self._drain_marker_policy
        if policy is None:
            return
        try:
            while self._is_running:
                await asyncio.sleep(5)
                if self._draining:
                    continue
                marker = self._read_drain_marker()
                try:
                    should = policy.drain_requested(
                        marker,
                        self._instantiation_epoch or "",
                        time.monotonic(),
                        last_handled_epoch=self._last_handled_drain_epoch,
                    )
                except Exception as e:
                    logger.debug("Gateway drain-marker evaluation error: %s", e)
                    continue
                if not should:
                    continue
                if isinstance(marker, dict):
                    self._last_handled_drain_epoch = marker.get("epoch")
                logger.info("Gateway honouring external drain marker")
                self._draining = True
                try:
                    await self._drain_active_sessions(
                        reason="drain-marker",
                        timeout=float(drain_timeout) if drain_timeout else 10.0,
                    )
                finally:
                    self._draining = False
        except asyncio.CancelledError:
            raise

    async def _drain_active_sessions(self, reason: str = "shutdown", timeout: float = 10.0) -> None:
        """Drain active sessions by waiting for in-flight executions to complete.
        
        Args:
            reason: Reason for draining (e.g., "shutdown", "restart")
            timeout: Maximum time to wait for sessions to complete
        """
        active_sessions = [
            session for session in self._sessions.values()
            if session._is_executing or not session._inbox.empty()
        ]
        
        if not active_sessions:
            return
        
        logger.info(f"Draining {len(active_sessions)} active sessions (reason: {reason})")
        
        # Give sessions time to complete
        start_time = time.monotonic()
        while active_sessions and (time.monotonic() - start_time) < timeout:
            # Check which sessions are still active
            still_active = []
            for session in active_sessions:
                if session._is_executing or not session._inbox.empty():
                    still_active.append(session)
                else:
                    # Session completed, persist it
                    if self._session_store:
                        try:
                            self._session_store.add_message(
                                session_id=session.session_id,
                                role="system",
                                content=f"Session drained: {reason}",
                                metadata={"session_data": session.to_dict()},
                            )
                        except Exception as e:
                            logger.error(f"Failed to persist drained session {session.session_id}: {e}")
            
            active_sessions = still_active
            if active_sessions:
                await asyncio.sleep(0.5)  # Brief wait before checking again
        
        # For any remaining active sessions, persist them as-is with pending work
        for session in active_sessions:
            logger.warning(f"Session {session.session_id} still active after drain timeout, persisting with pending work")
            if self._session_store:
                try:
                    # Add a session_end event before persisting
                    session.add_event(GatewayEvent(
                        type=EventType.SESSION_END,
                        data={
                            "session_id": session.session_id,
                            "reason": f"Force-closed during {reason} after timeout",
                            "had_pending_work": not session._inbox.empty(),
                            "was_executing": session._is_executing,
                        }
                    ))
                    
                    self._session_store.add_message(
                        session_id=session.session_id,
                        role="system",
                        content=f"Session force-closed during {reason} with pending work",
                        metadata={"session_data": session.to_dict()},
                    )
                except Exception as e:
                    logger.error(f"Failed to persist timed-out session {session.session_id}: {e}")

    async def stop(self, drain_timeout: float = 10.0) -> None:
        """Stop the gateway server with graceful drain.
        
        Args:
            drain_timeout: Maximum time to wait for active sessions to complete (default: 10.0)
        """
        if not self._is_running:
            return
        
        # Flip readiness to draining BEFORE draining so load balancers stop
        # routing new traffic while in-flight sessions finish. Keep _is_running
        # True so liveness (/live) still reports the process as alive during drain.
        self._draining = True
        
        # Gracefully drain active sessions before closing
        await self._drain_active_sessions(reason="shutdown", timeout=drain_timeout)
        
        self._is_running = False
        
        for client_id, ws in list(self._clients.items()):
            await self._teardown_client_conn(client_id)
            try:
                await ws.close()
            except Exception:
                pass
        
        self._clients.clear()
        self._client_conns.clear()
        self._client_sessions.clear()
        self._client_scopes.clear()
        self._client_auth_generation.clear()
        
        for session_id in list(self._sessions.keys()):
            self.close_session(session_id)
        
        if self._server:
            self._server.should_exit = True
        
        # Release PID lock
        if hasattr(self, '_pid_lock') and self._pid_lock:
            self._pid_lock.release_lock()
        
        logger.info("Gateway stopped")
    
    async def _handle_client_message(self, client_id: str, data: Dict[str, Any]) -> bool:
        """Handle a message from a client.

        Returns ``True`` when the frame was rejected as unauthorized (e.g.
        insufficient scope) so the caller's per-connection flood guard can
        count it; ``False``/``None`` otherwise. Existing callers that ignore
        the return value are unaffected.
        """
        msg_type = data.get("type", "message")
        
        # Handle versioned handshake
        if msg_type == "hello":
            agent_id = data.get("agent_id")
            
            # Check if agent exists
            if not agent_id or agent_id not in self._agents:
                error = HelloError(
                    code=ConnectErrorCode.AGENT_NOT_FOUND,
                    message=f"Agent not found: {agent_id}",
                    next_step=ConnectRecoveryStep.DO_NOT_RETRY,
                    next_action="check_agent_id",
                )
                await self._send_to_client(client_id, error.to_dict())
                return
            
            # Parse protocol version from client
            # Support both HelloParams format (protocol_min/max as direct fields)
            # and legacy format (nested under protocol dict)
            if "protocol_min" in data or "protocol_max" in data:
                # HelloParams format
                client_min = data.get("protocol_min", 1)
                client_max = data.get("protocol_max", 1)
            else:
                # Legacy format or missing
                protocol_info = data.get("protocol", {})
                if isinstance(protocol_info, dict):
                    client_min = protocol_info.get("min", 1)
                    client_max = protocol_info.get("max", 1)
                else:
                    # Backwards compatibility: treat missing protocol as v1
                    client_min = client_max = 1
            
            # Negotiate protocol version
            if client_max < MIN_CLIENT_PROTOCOL_VERSION:
                error = HelloError(
                    code=ConnectErrorCode.PROTOCOL_UNSUPPORTED,
                    message=f"Protocol version {client_max} is too old, minimum required is {MIN_CLIENT_PROTOCOL_VERSION}",
                    next_step=ConnectRecoveryStep.UPGRADE_CLIENT,
                    next_action="upgrade_client",
                )
                await self._send_to_client(client_id, error.to_dict())
                return
            
            if client_min > GATEWAY_PROTOCOL_VERSION:
                error = HelloError(
                    code=ConnectErrorCode.PROTOCOL_UNSUPPORTED,
                    message=f"Protocol version {client_min} is too new, server supports up to {GATEWAY_PROTOCOL_VERSION}",
                    next_step=ConnectRecoveryStep.DOWNGRADE_CLIENT,
                    next_action="use_older_client",
                )
                await self._send_to_client(client_id, error.to_dict())
                return
            
            # Select the highest mutually supported version
            negotiated_version = min(client_max, GATEWAY_PROTOCOL_VERSION)
            
            # Get client capabilities
            # Support both HelloParams format (capabilities) and legacy format (caps)
            client_caps = data.get("capabilities", data.get("caps", []))
            # Guard against null/None values
            if client_caps is None or not isinstance(client_caps, list):
                client_caps = []
            
            # Resume or create session
            session_id = data.get("session_id")
            since_cursor = data.get("since")
            session, replay_events = self.resume_or_create_session(
                session_id=session_id,
                agent_id=agent_id,
                client_id=client_id,
                since_cursor=since_cursor,
            )
            
            # Validate session belongs to requested agent
            if hasattr(session, 'agent_id') and session.agent_id != agent_id:
                error = HelloError(
                    code=ConnectErrorCode.AUTH_UNAUTHORIZED,
                    message="Session does not belong to the requested agent",
                    next_step=ConnectRecoveryStep.REAUTHENTICATE,
                    next_action="start_new_session",
                )
                await self._send_to_client(client_id, error.to_dict())
                return
            
            # Rebind client_id to session for correct routing
            if hasattr(session, '_client_id'):
                session._client_id = client_id
            
            # Record the negotiated protocol version and the client's advertised
            # capabilities on the session so they survive resume/persistence and
            # can be inspected by the server when tailoring delivery.
            session._protocol_version = negotiated_version
            session._capabilities = list(client_caps)
            
            self._client_sessions[client_id] = session.session_id
            
            # Build features list - only advertise implemented features
            features = {
                "methods": ["message", "leave"],  # abort not implemented
                "events": [
                    EventType.MESSAGE.value,
                    EventType.ERROR.value,
                ],
            }
            
            # Add streaming events if client supports streaming
            if "streaming" in client_caps:
                features["events"].extend([
                    EventType.TOKEN_STREAM.value,
                    EventType.TOOL_CALL_STREAM.value,
                    EventType.STREAM_END.value,
                ])
            
            # Add optional features based on client capabilities
            if "presence" in client_caps and hasattr(self, '_presence_tracker') and self._presence_tracker:
                features["events"].extend([
                    EventType.PRESENCE_JOIN.value,
                    EventType.PRESENCE_LEAVE.value,
                    EventType.PRESENCE_UPDATE.value,
                ])
            
            if "ack" in client_caps and hasattr(self, '_delivery_tracker') and self._delivery_tracker:
                features["events"].extend([
                    EventType.MESSAGE_ACK.value,
                    EventType.MESSAGE_NACK.value,
                    EventType.DELIVERY_RETRY.value,
                ])
            
            # Build policy limits - use configured values where available
            heartbeat_interval = getattr(self.config, 'heartbeat_interval', 30)
            policy = {
                "max_payload": getattr(self.config, 'max_payload', 1048576),  # 1MB default
                "max_buffered_bytes": getattr(self.config, 'max_buffered_bytes', 8388608),  # 8MB default
                "max_queued_frames": getattr(self.config, 'max_queued_frames', 1000),
                "heartbeat_ms": int(heartbeat_interval * 1000),  # Convert seconds to ms
            }
            
            # Send successful handshake response
            result = HelloResult(
                protocol=negotiated_version,
                features=features,
                policy=policy,
                session_id=session.session_id,
                resumed=session._was_resumed,
                cursor=session._event_cursor,
            )
            
            await self._send_to_client(client_id, {
                "type": "hello_ok",
                "protocol": result.protocol,
                "features": result.features,
                "policy": result.policy,
                "session_id": result.session_id,
                "resumed": result.resumed,
                "cursor": result.cursor,
            })
            
            # Replay missed events if any
            for event in replay_events:
                await self._send_to_client(client_id, {
                    "type": "replay",
                    "event": event.to_dict(),
                })
        
        # Keep backward compatibility with old join message
        elif msg_type == "join":
            agent_id = data.get("agent_id")
            if agent_id and agent_id in self._agents:
                # Protocol version negotiation with validation
                try:
                    client_min_version = int(data.get("min_version", MIN_PROTOCOL_VERSION))
                    client_max_version = int(data.get("max_version", PROTOCOL_VERSION))
                except (TypeError, ValueError):
                    await self._send_to_client(client_id, {
                        "type": "error",
                        "code": "invalid_protocol_hello",
                        "message": "Invalid protocol version fields. Expected integer min_version/max_version.",
                    })
                    return
                
                if client_min_version > client_max_version:
                    await self._send_to_client(client_id, {
                        "type": "error",
                        "code": "invalid_protocol_hello",
                        "message": f"Invalid version range: min_version ({client_min_version}) > max_version ({client_max_version})",
                    })
                    return
                
                # Check if we can negotiate a common version
                if client_max_version < MIN_PROTOCOL_VERSION or client_min_version > MAX_PROTOCOL_VERSION:
                    await self._send_to_client(client_id, {
                        "type": "error",
                        "code": "version_unsupported",
                        "message": f"Protocol version mismatch. Server supports {MIN_PROTOCOL_VERSION}-{MAX_PROTOCOL_VERSION}, client supports {client_min_version}-{client_max_version}",
                        "server_min_version": MIN_PROTOCOL_VERSION,
                        "server_max_version": MAX_PROTOCOL_VERSION,
                    })
                    return
                
                # Negotiate the highest common version
                negotiated_version = min(client_max_version, MAX_PROTOCOL_VERSION)
                
                # Support reconnection with existing session
                session_id = data.get("session_id")  # Optional: existing session to resume
                # Parse and validate the since parameter
                since_raw = data.get("since")  # Optional: cursor for event replay
                since_cursor = None
                if since_raw is not None:
                    try:
                        since_cursor = int(since_raw)
                    except (TypeError, ValueError):
                        await self._send_to_client(client_id, {
                            "type": "error",
                            "message": "Invalid 'since' cursor. Must be an integer.",
                        })
                        return
                
                # Resume or create session
                session, replay_events = self.resume_or_create_session(
                    session_id=session_id,
                    agent_id=agent_id,
                    client_id=client_id,
                    since_cursor=since_cursor,
                )
                
                # Set negotiated protocol version for the session
                session._protocol_version = negotiated_version
                
                self._client_sessions[client_id] = session.session_id
                
                # Check if resync is required
                resync_required = session.check_resync_required(since_cursor)
                oldest_cursor = session.get_oldest_cursor()
                
                # Build presence snapshot
                presence_snapshot = []
                if hasattr(self, '_presence_manager'):
                    from .push_presence import PresenceManager
                    if isinstance(self._presence_manager, PresenceManager):
                        presence_info = self._presence_manager.get_all_presence()
                        presence_snapshot = [p.to_dict() for p in presence_info]
                
                # Calculate correct sequence for replay
                joined_sequence = session._sequence
                if replay_events and replay_events[0].sequence is not None:
                    joined_sequence = replay_events[0].sequence - 1
                
                # Send join confirmation with protocol info, integrity checks, and snapshot
                await self._send_to_client(client_id, {
                    "type": "joined",
                    "session_id": session.session_id,
                    "agent_id": agent_id,
                    "resumed": session._was_resumed,
                    "cursor": session._event_cursor,
                    "oldest_cursor": oldest_cursor,
                    "resync_required": resync_required,
                    "sequence": joined_sequence,  # Sequence aligned with replay events
                    "protocol_version": negotiated_version,
                    "server_min_version": MIN_PROTOCOL_VERSION,
                    "server_max_version": MAX_PROTOCOL_VERSION,
                    "presence": presence_snapshot,  # Presence snapshot
                    "health": self.health(),  # Health status
                })
                
                if resync_required:
                    # Send authoritative snapshot instead of partial replay
                    snapshot = session.get_snapshot()
                    await self._send_to_client(client_id, {
                        "type": "snapshot",
                        "state": snapshot,
                    })
                else:
                    # Replay missed events if any
                    for event in replay_events:
                        event_data = event.to_dict()
                        # Include top-level sequence number from the cursor
                        seq = event.data.get('cursor', 0)
                        await self._send_to_client(client_id, {
                            "type": "replay",
                            "event": event_data,
                            "seq": seq,
                        })
                
                # If session was resumed with pending messages or was executing, restart processing
                if session._was_resumed and (not session._inbox.empty() or session._is_executing):
                    agent = self._agents.get(agent_id)
                    if agent:
                        logger.info(f"Resuming processing for session {session.session_id} with {session._inbox.qsize()} pending messages")
                        # Notify client that we're resuming processing
                        await self._send_to_client(client_id, {
                            "type": "status",
                            "source": session.agent_id,
                            "message": f"Resuming processing ({session._inbox.qsize()} pending messages)...",
                        })
                        # CRITICAL FIX: Mark executing BEFORE creating the task to prevent race condition
                        # where a new message arrives before the task starts and spawns a duplicate task
                        if not session._is_executing:
                            session.mark_executing(True)
                        # Restart the queue processor
                        asyncio.create_task(self._run_session_queue(session, agent, client_id))
            else:
                await self._send_to_client(client_id, {
                    "type": "error",
                    "message": f"Agent not found: {agent_id}",
                })
        
        elif msg_type == "message":
            # Sending a message as the agent requires the WRITE scope.
            if not self._client_has_scope(client_id, OperatorScope.WRITE):
                await self._send_to_client(client_id, {
                    "type": "error",
                    "code": "insufficient_scope",
                    "message": "insufficient scope",
                    "required_scope": OperatorScope.WRITE.value,
                })
                return True
            session_id = self._client_sessions.get(client_id)
            if session_id:
                session = self._sessions.get(session_id)
                if session:
                    content = data.get("content", "")
                    message = GatewayMessage(
                        content=content,
                        sender_id=client_id,
                        session_id=session_id,
                    )
                    session.add_message(message)
                    
                    response = await self._process_agent_message(session, message)
                    
                    await self._send_to_client(client_id, {
                        "type": "response",
                        "content": response,
                        "session_id": session_id,
                    })
            else:
                await self._send_to_client(client_id, {
                    "type": "error",
                    "message": "Not joined to any session",
                })
        
        elif msg_type == "leave":
            session_id = self._client_sessions.pop(client_id, None)
            if session_id:
                # Close session but keep it persisted for resumption
                self.close_session(session_id, persist=True)
                await self._send_to_client(client_id, {
                    "type": "left",
                    "session_id": session_id,
                })
    
    async def _process_agent_message(
        self,
        session: GatewaySession,
        message: GatewayMessage,
    ) -> str:
        """Process a message through the agent.
        
        If the agent has a stream_emitter, registers a callback that relays
        token deltas to the connected WebSocket client in real-time via
        TOKEN_STREAM / TOOL_CALL_STREAM / STREAM_END events.
        """
        agent = self._agents.get(session.agent_id)
        if not agent:
            return "Agent not available"
        
        client_id = session.client_id
        content = message.content if isinstance(message.content, str) else str(message.content)
        
        # Inbox & Stepper logic
        if session._is_executing:
            # Send an ephemeral status event
            await self._send_to_client(
                client_id,
                {
                    "type": "status",
                    "source": session.agent_id,
                    "message": "Thinking... (I've added your new message to the queue to process next)."
                }
            )
            await session.queue_message(content)
            return "Message queued."
            
        session.mark_executing(True)
        await session.queue_message(content)
        
        # Start background task to process the queue
        asyncio.create_task(self._run_session_queue(session, agent, client_id))
        return "Started processing."

    @staticmethod
    async def _dispatch_agent_turn(agent: Any, content: str) -> Any:
        """Execute a single agent turn.

        Prefers the agent's native async entry point (``arun``/``achat``) so
        turns run directly on the event loop, giving native asyncio concurrency,
        cleaner cancellation/timeout and true async streaming. Falls back to
        offloading the synchronous ``chat`` onto the default thread pool only
        when no async entry point is available (sync-only agents).
        """
        for _name in ("arun", "achat"):
            _fn = getattr(agent, _name, None)
            if _fn is not None and asyncio.iscoroutinefunction(_fn):
                return await _fn(content)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, agent.chat, content)

    async def _run_session_queue(self, session: GatewaySession, agent: Any, client_id: str) -> None:
        """Background task loop that constantly pulls from `_inbox` and executes the agent task."""
        try:
            while True:
                content = session.get_next_message()
                if not content:
                    break  # Queue is empty, exit loop
                
                # Wire streaming relay if agent has a stream_emitter
                relay_callback = None
                emitter = getattr(agent, 'stream_emitter', None)
                if emitter is not None and client_id:
                    relay_callback = self._make_stream_relay(client_id, session)
                    emitter.add_callback(relay_callback)
                
                try:
                    gate = getattr(self, "_admission_gate", None)
                    if gate is not None and getattr(gate, "enabled", False):
                        # Gateway-wide inbound admission ceiling (#2454). The
                        # direct WebSocket path bypasses the bot-session gate,
                        # so enforce the shared gate here too.
                        from ..bots._admission import AdmissionRejected
                        try:
                            async with gate.admit(session_id=session.session_id):
                                response = await self._dispatch_agent_turn(
                                    agent, content
                                )
                        except AdmissionRejected as rej:
                            response = rej.message
                    else:
                        response = await self._dispatch_agent_turn(agent, content)
                except Exception as e:
                    logger.error(f"Agent error in queue processor: {e}")
                    response = f"Error: {str(e)}"
                finally:
                    # Always clean up the relay callback
                    if relay_callback and emitter is not None:
                        try:
                            emitter.remove_callback(relay_callback)
                        except (ValueError, AttributeError):
                            pass
                
                response_message = GatewayMessage(
                    content=response,
                    sender_id=session.agent_id,
                    session_id=session.session_id,
                )
                session.add_message(response_message)
                
                await self._send_to_client(client_id, {
                    "type": "response",
                    "content": response,
                    "session_id": session.session_id,
                })
        finally:
            session.mark_executing(False)

    def _make_stream_relay(
        self, client_id: str, session: "GatewaySession"
    ) -> Callable:
        """Create a StreamCallback that relays events to a WS client."""
        gateway = self
        # Capture the running loop while we are still on it.
        loop = asyncio.get_running_loop()

        def _relay(event) -> None:
            try:
                from praisonaiagents.streaming.events import StreamEventType
                
                event_type = getattr(event, 'type', None)
                if event_type is None:
                    return
                
                # Map StreamEventType -> gateway EventType
                if event_type == StreamEventType.DELTA_TEXT:
                    gw_type = EventType.TOKEN_STREAM
                    data = {
                        "content": getattr(event, 'content', ''),
                        "session_id": session.session_id,
                    }
                elif event_type == StreamEventType.DELTA_TOOL_CALL:
                    gw_type = EventType.TOOL_CALL_STREAM
                    data = {
                        "tool_call": getattr(event, 'tool_call', {}),
                        "session_id": session.session_id,
                    }
                elif event_type == StreamEventType.STREAM_END:
                    gw_type = EventType.STREAM_END
                    data = {"session_id": session.session_id}
                else:
                    return  # Skip non-essential events
                
                gw_event = GatewayEvent(
                    type=gw_type,
                    data=data,
                    source=session.agent_id,
                    target=client_id,
                )
                
                # No get_event_loop() in the threaded callback.
                asyncio.run_coroutine_threadsafe(
                    gateway._send_to_client(client_id, gw_event.to_dict()),
                    loop,
                )
            except Exception:
                logger.warning("Stream relay error (non-fatal)", exc_info=True)

        return _relay
    
    def _register_client_conn(self, client_id: str, websocket: Any) -> "_ClientConn":
        """Create and start a bounded outbound connection for a client."""
        conn = _ClientConn(
            websocket,
            client_id,
            max_buffered_bytes=getattr(self.config, "max_buffered_bytes", 1024 * 1024),
            max_queued_frames=getattr(self.config, "max_queued_frames", 1000),
        )
        conn.start()
        self._client_conns[client_id] = conn
        return conn

    async def _teardown_client_conn(self, client_id: str) -> None:
        """Stop and remove a client's bounded outbound connection."""
        conn = self._client_conns.pop(client_id, None)
        if conn is not None:
            await conn.close()

    async def _evict_slow_consumer(self, client_id: str) -> None:
        """Evict a slow/stalled consumer with a typed SLOW_CONSUMER close.

        Closing isolates a genuinely slow client so its unbounded backlog can
        neither grow without limit nor delay delivery to healthy clients.
        """
        logger.warning(
            "Evicting slow consumer %s (outbound buffer exceeded "
            "max_buffered_bytes=%s / max_queued_frames=%s)",
            client_id,
            getattr(self.config, "max_buffered_bytes", None),
            getattr(self.config, "max_queued_frames", None),
        )
        ws = self._clients.pop(client_id, None)
        await self._teardown_client_conn(client_id)
        # Mirror the normal disconnect cleanup so evicted clients do not leave
        # stale scope/session entries that accumulate until shutdown.
        self._client_scopes.pop(client_id, None)
        self._client_auth_generation.pop(client_id, None)
        session_id = self._client_sessions.pop(client_id, None)
        if session_id:
            self.close_session(session_id)
        if ws is not None:
            try:
                await ws.close(
                    code=SLOW_CONSUMER_CLOSE_CODE,
                    reason=GatewayCloseCode.SLOW_CONSUMER.value,
                )
            except Exception as exc:
                logger.debug(
                    "Could not close slow consumer %s: %s", client_id, exc
                )

    def _auth_generation(self) -> str:
        """Return a stable fingerprint of the *active* shared secret.

        Issue #2661: each authenticated client is stamped with this value at
        connect time; when ``auth_token`` is rotated the fingerprint changes
        and :meth:`_revoke_rotated_sessions` can force-close every session that
        still carries the old stamp. The raw secret is never logged or stored —
        only a truncated SHA-256 digest — so the stamp is safe to keep in
        memory and compare. An empty/absent secret (local loopback mode) maps
        to a stable sentinel so those sessions are handled consistently.
        """
        token = getattr(self.config, "auth_token", None) or ""
        if not token:
            return "no-auth"
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]

    async def _revoke_rotated_sessions(self) -> int:
        """Force-close every session that authenticated under a stale secret.

        Issue #2661: after the shared ``auth_token`` is rotated (via config
        hot-reload or an explicit operator action) this evicts every live
        WebSocket session whose stamped auth generation no longer matches the
        active one, using the existing force-close path. Evicted clients are
        told to re-authenticate (structured ``CREDENTIALS_ROTATED`` close code +
        ``REAUTHENTICATE`` recovery step) rather than back off, and sessions
        already on the current secret are left untouched.

        Returns:
            The number of sessions revoked.
        """
        current = self._auth_generation()
        stale = [
            client_id
            for client_id, generation in list(self._client_auth_generation.items())
            if generation != current
        ]
        if not stale:
            return 0
        logger.warning(
            "Revoking %d gateway session(s) after auth secret rotation",
            len(stale),
        )
        for client_id in stale:
            await self._force_close_credentials_rotated(client_id)
        return len(stale)

    async def _force_close_credentials_rotated(self, client_id: str) -> None:
        """Force-close one session whose credential was rotated/revoked.

        Reuses the same server-initiated close mechanism as slow-consumer
        eviction, swapping in the structured ``CREDENTIALS_ROTATED`` reason so
        clients branch deterministically on ``(code, next_step)`` and
        re-authenticate.
        """
        ws = self._clients.pop(client_id, None)
        await self._teardown_client_conn(client_id)
        self._client_scopes.pop(client_id, None)
        self._client_auth_generation.pop(client_id, None)
        session_id = self._client_sessions.pop(client_id, None)
        if session_id:
            self.close_session(session_id)
        if ws is not None:
            try:
                await ws.close(
                    code=CREDENTIALS_ROTATED_CLOSE_CODE,
                    reason=GatewayCloseCode.CREDENTIALS_ROTATED.value,
                )
            except Exception as exc:
                logger.debug(
                    "Could not close rotated-credential session %s: %s",
                    client_id,
                    exc,
                )

    async def _send_to_client(self, client_id: str, data: Dict[str, Any]) -> None:
        """Send data to a specific client through its bounded outbound queue."""
        ws = self._clients.get(client_id)
        if ws:
            try:
                # Track event in session BEFORE sending if it's a response or important event
                if data.get("type") in [
                    "response",
                    "message",
                    "stream_end",
                    "error",
                    "token_stream",
                    "tool_call_stream",
                ]:
                    session_id = self._client_sessions.get(client_id)
                    if session_id:
                        session = self._sessions.get(session_id)
                        if session:
                            event = GatewayEvent(
                                type=data.get("type", "message"),
                                data=data,
                                source="gateway",
                                target=client_id,
                            )
                            cursor = session.add_event(event)
                            # Add cursor to the data BEFORE sending
                            data["cursor"] = cursor
                            # Add top-level sequence number for integrity checking
                            data["seq"] = cursor

                # Offer to the per-client bounded queue (isolated, drained by
                # its own task). A genuine slow consumer is evicted rather than
                # allowed to grow an unbounded backlog or stall other clients.
                conn = self._client_conns.get(client_id)
                if conn is not None:
                    # Offer a per-client snapshot: ``cursor``/``seq`` are
                    # client-specific and the caller may reuse the same ``data``
                    # dict across subscribers, so queue a copy to avoid a later
                    # call overwriting a not-yet-drained frame.
                    if not conn.offer(dict(data)):
                        await self._evict_slow_consumer(client_id)
                else:
                    # No bounded conn (e.g. directly registered client) — fall
                    # back to a best-effort direct send for compatibility.
                    await ws.send_json(data)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
    
    def register_agent(
        self,
        agent: "Agent",
        agent_id: Optional[str] = None,
        *,
        overwrite: bool = True,
    ) -> str:
        """Register an agent with the gateway.
        
        Args:
            agent: The agent instance to register
            agent_id: Optional custom ID (auto-generated if not provided)
            overwrite: If False, raises ValueError on duplicate ID (default: True for backward compat)
            
        Returns:
            The agent ID used for registration
            
        Raises:
            ValueError: If overwrite=False and agent_id already exists
        """
        aid = agent_id or getattr(agent, "agent_id", None) or str(uuid.uuid4())
        
        # B10: Handle duplicate registration
        if aid in self._agents:
            if not overwrite:
                raise ValueError(
                    f"Agent '{aid}' already registered. Use overwrite=True to replace."
                )
            logger.warning(f"Overwriting existing agent: {aid}")
        
        self._agents[aid] = agent
        logger.info(f"Agent registered: {aid}")
        return aid
    
    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the gateway."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Agent unregistered: {agent_id}")
            return True
        return False
    
    def get_agent(self, agent_id: str) -> Optional["Agent"]:
        """Get a registered agent by ID."""
        return self._agents.get(agent_id)
    
    def list_agents(self) -> List[str]:
        """List all registered agent IDs."""
        return list(self._agents.keys())
    
    # ── Client Management (Public API) ────────────────────────────────
    
    def add_client(self, client_id: str, websocket: Any) -> None:
        """Register a client WebSocket connection.
        
        Args:
            client_id: Unique client identifier
            websocket: WebSocket connection object
        """
        self._clients[client_id] = websocket
        self._register_client_conn(client_id, websocket)
        logger.debug(f"Client added: {client_id}")
    
    def remove_client(self, client_id: str) -> bool:
        """Unregister a client connection.
        
        Args:
            client_id: The client ID to remove
            
        Returns:
            True if client was found and removed, False otherwise
        """
        removed = self._clients.pop(client_id, None) is not None
        conn = self._client_conns.pop(client_id, None)
        if conn is not None:
            # Best-effort async teardown of the drain task; schedule it on the
            # running loop when one is available, otherwise drop the reference.
            try:
                asyncio.ensure_future(conn.close())
            except RuntimeError:
                pass
        if removed:
            logger.debug(f"Client removed: {client_id}")
        return removed
    
    def get_client(self, client_id: str) -> Optional[Any]:
        """Get a client WebSocket by ID.
        
        Args:
            client_id: The client ID to look up
            
        Returns:
            The WebSocket connection or None if not found
        """
        return self._clients.get(client_id)
    
    def list_clients(self) -> List[str]:
        """List all connected client IDs.
        
        Returns:
            List of client IDs
        """
        return list(self._clients.keys())
    
    # ── Channel Bot Management (Public API - B7) ─────────────────────────
    
    def list_channel_bots(self) -> List[str]:
        """List all registered channel bot names.
        
        Returns:
            List of channel bot names (e.g., ['discord', 'telegram'])
        """
        return list(self._channel_bots.keys())
    
    def get_channel_bot(self, name: str) -> Optional[Any]:
        """Get a channel bot by name.
        
        Args:
            name: The channel bot name (e.g., 'discord', 'telegram')
            
        Returns:
            The bot instance or None if not found
        """
        return self._channel_bots.get(name)

    def _resolve_channel_bot(self, name: str) -> Optional[Any]:
        """Resolve a channel bot with the gateway's case-insensitive fallback.

        Mirrors the lookup the ``_deliver_*`` fallbacks use so a configured
        "Telegram" resolves a "telegram" target and vice versa.
        """
        bot = self._channel_bots.get(name)
        if bot is not None:
            return bot
        for candidate_name, candidate in self._channel_bots.items():
            if candidate_name.lower() == name.lower():
                return candidate
        return None

    def has_channel_bot(self, name: str) -> bool:
        """Check if a channel bot is registered.
        
        Args:
            name: The channel bot name
            
        Returns:
            True if the bot exists, False otherwise
        """
        return name in self._channel_bots

    # ── Inbound trigger hooks (Public API - Issue #2281) ─────────────────

    def register_hook(
        self,
        hook: "Any" = None,
        *,
        path: Optional[str] = None,
        agent: Optional[str] = None,
        action: str = "agent",
        auth: Optional[str] = None,
        session_key: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        deliver_to: Optional[str] = None,
        message_template: Optional[str] = None,
        message: Optional[str] = None,
        enabled: bool = True,
    ) -> str:
        """Register an inbound trigger that exposes ``POST /hooks/<path>``.

        On a request, the gateway authenticates, deduplicates by an idempotency
        key derived from the payload, resolves a session from a templated
        ``session_key``, runs the configured agent on a templated ``message``
        (or, with ``action="wake"``, nudges an existing session), then delivers
        the reply through the delivery router to ``deliver_to``.

        Args:
            hook: An existing ``HookConfig`` or a dict; mutually exclusive with
                the keyword form.
            path: URL segment, e.g. ``"gmail"`` -> ``POST /hooks/gmail``.
            agent: Agent id to run (defaults to the first registered agent).
            action: ``"agent"`` runs a turn, ``"wake"`` nudges a session.
            auth: Bearer token required on the request (defaults to the
                gateway ``auth_token``).
            session_key: Template for the session id.
            idempotency_key: Template for the dedup key.
            deliver_to: ``channel:target`` to deliver the reply to.
            message_template / message: Template for the agent message.
            enabled: Whether the hook is active.

        Returns:
            The registered hook path.
        """
        from praisonaiagents.gateway import HookConfig

        if hook is not None:
            if isinstance(hook, dict):
                cfg = HookConfig.from_dict(hook)
            else:
                cfg = hook  # assume HookConfig-like
        else:
            cfg = HookConfig(
                path=path or "",
                agent=agent,
                action=action,
                auth=auth,
                session_key=session_key,
                idempotency_key=idempotency_key,
                deliver_to=deliver_to,
                message=message_template if message_template is not None else message,
                enabled=enabled,
            )

        self._hooks[cfg.path] = cfg
        logger.info("Inbound hook registered: POST /hooks/%s", cfg.path)
        return cfg.path

    def unregister_hook(self, path: str) -> bool:
        """Remove a registered hook by path."""
        key = (path or "").strip().strip("/")
        if key in self._hooks:
            del self._hooks[key]
            logger.info("Inbound hook unregistered: %s", key)
            return True
        return False

    def list_hooks(self) -> List[str]:
        """List registered hook paths."""
        return list(self._hooks.keys())

    def get_hook(self, path: str) -> Optional[Any]:
        """Get a registered hook config by path."""
        return self._hooks.get((path or "").strip().strip("/"))

    def _register_hooks_from_config(self, hooks_cfg: Any) -> None:
        """Register inbound trigger hooks from a parsed YAML ``hooks:`` list.

        Accepts either a list of dicts or a list of ``HookConfig`` objects.
        Invalid entries are skipped with a warning rather than aborting startup.
        """
        for entry in hooks_cfg or []:
            try:
                self.register_hook(entry)
            except (ValueError, TypeError) as e:
                logger.warning("Skipping invalid hook config %s: %s", entry, e)

    def _apply_hooks_from_config(self, cfg: Dict[str, Any]) -> None:
        """Rebuild the hook registry from a parsed gateway config.

        Clears any previously registered hooks before re-registering so that a
        config reload picks up removed hooks and rotated secrets without a full
        process restart. Hooks may live at the top level (``hooks:``) or nested
        under ``gateway:`` for grouping.
        """
        hooks_cfg = cfg.get("hooks")
        if hooks_cfg is None:
            hooks_cfg = cfg.get("gateway", {}).get("hooks")
        self._hooks.clear()
        if hooks_cfg:
            self._register_hooks_from_config(hooks_cfg)

    def _hook_reserve(self, key: str) -> bool:
        """Atomically claim ``key`` for processing.

        Returns ``True`` when the caller may proceed, ``False`` when the key was
        already recorded *or* is currently being processed by a concurrent
        request. This check-and-reserve runs entirely synchronously (no
        ``await``), so on the single-threaded event loop it is atomic and closes
        the time-of-check/time-of-use race between the seen-check and the
        deferred :meth:`_hook_record`.

        On a falsy outcome the caller must release the reservation via
        :meth:`_hook_release`; on success it must call :meth:`_hook_record`.
        Expired entries are pruned lazily here.
        """
        now = time.time()
        store = self._hook_idempotency
        # Prune expired entries lazily.
        if store:
            ttl = self._hook_idempotency_ttl
            expired = [k for k, ts in store.items() if now - ts > ttl]
            for k in expired:
                store.pop(k, None)
        if key in store or key in self._hook_inflight:
            return False
        self._hook_inflight.add(key)
        return True

    def _hook_release(self, key: str) -> None:
        """Release an in-flight reservation so the delivery can be retried."""
        self._hook_inflight.discard(key)

    def _hook_record(self, key: str) -> None:
        """Record ``key`` as processed. Bounded so the store cannot grow unboundedly."""
        self._hook_inflight.discard(key)
        store = self._hook_idempotency
        store[key] = time.time()
        # Enforce max size (drop oldest).
        while len(store) > self._hook_idempotency_max:
            store.popitem(last=False)

    async def _run_hook(self, hook: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a hook: resolve session, run agent (or wake), deliver.

        Returns a JSON-serializable result dict describing what happened.
        """
        session_key = hook.resolve_session_key(payload)

        # action == "wake": just nudge an existing session, no new turn.
        if hook.action == "wake":
            session = self._sessions.get(session_key)
            if session is not None:
                session._last_activity = time.time()
            return {"ok": True, "action": "wake", "session": session_key}

        # action == "agent": resolve agent, run a turn on the templated message.
        agent_id = hook.agent
        if agent_id:
            # An explicitly configured agent that is not registered is an error,
            # not a reason to silently run an unrelated agent.
            agent = self._agents.get(agent_id)
            if agent is None:
                return {
                    "ok": False,
                    "error": f"agent '{agent_id}' not available",
                    "session": session_key,
                }
        else:
            # No agent configured: fall back to the first registered agent.
            agent = next(iter(self._agents.values()), None)
            agent_id = next(iter(self._agents.keys()), None) if self._agents else None

        if agent is None:
            return {"ok": False, "error": "no agent available", "session": session_key}

        message = hook.resolve_message(payload) or ""

        try:
            gate = getattr(self, "_admission_gate", None)
            if gate is not None and getattr(gate, "enabled", False):
                # Gateway-wide inbound admission ceiling (#2454). Hook-triggered
                # runs are a distinct inbound surface; route them through the
                # shared gate so a burst of POST /hooks/<path> requests cannot
                # exceed max_concurrent_runs and recreate the overload it guards.
                from ..bots._admission import AdmissionRejected
                try:
                    async with gate.admit(session_id=session_key):
                        reply = await self._dispatch_agent_turn(agent, message)
                except AdmissionRejected as rej:
                    return {
                        "ok": False,
                        "error": rej.message,
                        "action": "agent",
                        "agent": agent_id,
                        "session": session_key,
                        "rejected": True,
                    }
            else:
                reply = await self._dispatch_agent_turn(agent, message)
        except Exception as e:  # noqa: BLE001 - report run failure to caller
            logger.error("Hook '%s' agent run failed: %s", hook.path, e)
            return {"ok": False, "error": str(e), "session": session_key}

        reply_text = reply if isinstance(reply, str) else str(reply)

        delivered = None
        if hook.deliver_to and reply_text:
            delivered = await self._deliver_hook_reply(hook.deliver_to, reply_text)
            if not delivered:
                # Configured delivery failed: surface as a failure so the key is
                # not recorded and the sender can retry.
                return {
                    "ok": False,
                    "error": "hook reply delivery failed",
                    "action": "agent",
                    "agent": agent_id,
                    "session": session_key,
                    "delivered": False,
                }

        return {
            "ok": True,
            "action": "agent",
            "agent": agent_id,
            "session": session_key,
            "delivered": delivered,
        }

    @property
    def delivery_router(self) -> Optional[Any]:
        """Resilient outbound router for the gateway's scheduled/hook path.

        Issue #2624: previously ``_deliver_scheduled_result`` and
        ``_deliver_hook_reply`` called ``bot.send_message()`` directly, so the
        gateway's unattended-automation path had weaker guarantees than the
        interactive BotOS path — a re-fired job could double-post, a burst
        could trip 429s unthrottled, and a permanently-gone chat was retried
        forever. Routing both paths through the existing
        :class:`~praisonai.bots.delivery.DeliveryRouter` gives them the same
        token-bucket rate limiting, LRU idempotency dedup, and self-healing
        dead-target suppression.

        Built lazily so it always reflects the current ``_channel_bots`` and so
        the import cost is only paid when a scheduled/hook delivery occurs.
        Returns ``None`` (callers fall back to a bare send) only if the router
        cannot be imported, preserving delivery even without the bots package.
        """
        if self._delivery_router is not None:
            return self._delivery_router
        try:
            from praisonai_bot.bots.delivery import DeliveryRouter
            from praisonai_bot.bots import DeadTargetRegistry
        except Exception as e:  # pragma: no cover - defensive import guard
            logger.debug(
                "DeliveryRouter unavailable for gateway delivery: %s", e,
            )
            return None
        try:
            # Issue #3139: back the dead-target registry with the canonical
            # SQLite ``dead_targets`` table (shared ``DeliveryControlStore``)
            # instead of the node-local ``dead_targets.json`` sidecar, so the
            # single source of truth is the same crash-safe, cross-worker store
            # the outbox/DLQ/rate-limiter already use. Falls back to the JSON
            # default only if the SQLite store cannot be constructed.
            dead_store = None
            try:
                from pathlib import Path
                from praisonai_bot.bots._delivery_control_store import (
                    DeliveryControlStore,
                )

                dead_store = DeliveryControlStore(
                    Path.home() / ".praisonai" / "state" / "delivery_control.sqlite"
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.debug(
                    "DeliveryControlStore unavailable, using JSON dead-target "
                    "sidecar: %s",
                    e,
                )
            self._dead_targets = DeadTargetRegistry(store=dead_store)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("DeadTargetRegistry unavailable: %s", e)
            self._dead_targets = None
        botos = _ChannelBotOS(self._channel_bots)
        self._delivery_router = DeliveryRouter(botos, dead_targets=self._dead_targets)
        return self._delivery_router

    async def _deliver_hook_reply(self, deliver_to: str, text: str) -> bool:
        """Deliver a hook reply to a ``channel:target`` via the router.

        Issue #2624: routes through :attr:`delivery_router` so hook replies gain
        rate-limiting, idempotency dedup, and dead-target suppression identical
        to the scheduled path. Falls back to the prior bare send only if the
        router cannot be constructed.
        """
        if ":" not in deliver_to:
            logger.warning(
                "Hook deliver_to '%s' must be 'channel:target'; skipping",
                deliver_to,
            )
            return False
        channel, target = [p.strip() for p in deliver_to.split(":", 1)]

        router = self.delivery_router
        if router is not None:
            delivered = await router.deliver(
                f"{channel}:{target}",
                text,
                idempotency_key=f"hook:{channel}:{target}:{_delivery_text_digest(text)}",
            )
            if delivered:
                logger.info("Hook delivered reply to %s:%s", channel, target)
            else:
                logger.error("Hook delivery to %s:%s failed", channel, target)
            return delivered

        # Fallback: router unavailable — preserve the prior bare-send behaviour.
        bot = self.get_channel_bot(channel)
        if bot is None:
            for name, b in self._channel_bots.items():
                if name.lower() == channel.lower():
                    bot = b
                    break
        if bot is None:
            logger.warning("No channel bot '%s' for hook delivery", channel)
            return False
        try:
            await bot.send_message(target, text)
            logger.info("Hook delivered reply to %s:%s", channel, target)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Hook delivery to %s:%s failed: %s", channel, target, e)
            return False

    def create_session(
        self,
        agent_id: str,
        client_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GatewaySession:
        """Create a new session or resume an existing one."""
        sid = session_id or str(uuid.uuid4())
        
        # Check if session exists in memory first
        if sid in self._sessions:
            session = self._sessions[sid]
            if session.is_active:
                logger.info(f"Session already active in memory: {sid}")
                return session
        
        # Try to rehydrate from persistent store
        if session_id and self._session_store and self._session_store.session_exists(session_id):
            try:
                # Rehydrate session from store - get full session data with metadata
                session_data_obj = self._session_store.get_session(session_id)
                
                # Load session metadata if stored
                session_data = None
                
                # Use the latest session_data snapshot (close writes after init).
                for msg in session_data_obj.messages:
                    if msg.role == 'system' and msg.metadata and 'session_data' in msg.metadata:
                        session_data = msg.metadata['session_data']
                
                # Restore session from persisted data
                if session_data:
                    session = GatewaySession.from_dict(session_data, self.config.session_config.max_messages)
                else:
                    # Fallback: create new session but restore messages
                    session = GatewaySession(
                        _session_id=sid,
                        _agent_id=agent_id,
                        _client_id=client_id,
                        _max_messages=self.config.session_config.max_messages,
                    )
                    # Mark as resumed since we're restoring from persistence
                    session._was_resumed = True
                    # Restore messages from history
                    for msg in session_data_obj.messages:
                        if msg.role in ['user', 'assistant']:
                            gateway_msg = GatewayMessage(
                                content=msg.content,
                                sender_id=msg.role,
                                session_id=sid,
                                timestamp=msg.timestamp,
                                metadata=msg.metadata or {},
                            )
                            session.add_message(gateway_msg)
                
                session._is_active = True  # Reactivate the session
                self._sessions[sid] = session
                logger.info(f"Session resumed from persistent store: {sid} for agent {agent_id}")
                return session
            except Exception as e:
                logger.warning(f"Failed to rehydrate session {sid}: {e}. Creating new session.")
        
        # Create new session
        session = GatewaySession(
            _session_id=sid,
            _agent_id=agent_id,
            _client_id=client_id,
            _max_messages=self.config.session_config.max_messages,
        )
        self._sessions[sid] = session
        
        # Persist initial session state if store is configured
        if self._session_store:
            try:
                # Store session metadata as first system message
                self._session_store.add_message(
                    session_id=sid,
                    role="system",
                    content="Session initialized",
                    metadata={"session_data": session.to_dict()},
                )
            except Exception as e:
                logger.warning(f"Failed to persist initial session state: {e}")
        
        logger.info(f"Session created: {sid} for agent {agent_id}")
        return session
    
    def get_session(self, session_id: str) -> Optional[GatewaySession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def close_session(self, session_id: str, persist: bool = True) -> bool:
        """Close a session, optionally persisting it for later resumption.
        
        Args:
            session_id: The session ID to close
            persist: Whether to persist the session for later resumption (default: True)
        
        Returns:
            True if session was closed, False if not found
        """
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        session.close()
        
        # Persist session state before removing from memory if configured
        if persist and self._session_store:
            try:
                # Save final session state
                self._session_store.add_message(
                    session_id=session_id,
                    role="system",
                    content="Session closed",
                    metadata={"session_data": session.to_dict()},
                )
                # Set TTL for session cleanup
                resume_window = self.config.session_config.resume_window
                self._session_ttls[session_id] = time.time() + resume_window
                logger.info(f"Session {session_id} persisted, resumable for {resume_window}s")
            except Exception as e:
                logger.warning(f"Failed to persist session state on close: {e}")
        
        # Remove from active sessions
        self._sessions.pop(session_id, None)
        
        logger.info(f"Session closed: {session_id}")
        return True
    
    def list_sessions(self, agent_id: Optional[str] = None) -> List[str]:
        """List session IDs, optionally filtered by agent."""
        if agent_id:
            return [
                sid for sid, session in self._sessions.items()
                if session.agent_id == agent_id
            ]
        return list(self._sessions.keys())
    
    def resume_or_create_session(
        self,
        session_id: Optional[str],
        agent_id: str,
        client_id: Optional[str] = None,
        since_cursor: Optional[int] = None,
    ) -> tuple[GatewaySession, List[GatewayEvent]]:
        """Resume an existing session or create a new one, with event replay.
        
        Args:
            session_id: Existing session ID to resume (None to create new)
            agent_id: Agent ID for the session
            client_id: Client ID
            since_cursor: Cursor position to replay events from
        
        Returns:
            Tuple of (session, replay_events) where replay_events are events
            that occurred after since_cursor. Note: Callers must check
            session.check_resync_required(since_cursor) before using replay_events,
            as the events may not include the full gap if buffer was trimmed.
        """
        replay_events = []
        
        # Try to resume existing session
        if session_id:
            session = self.get_session(session_id)
            if not session and self._session_store and self._session_store.session_exists(session_id):
                # Rehydrate from store
                session = self.create_session(agent_id, client_id, session_id)
            
            if session:
                # Get events to replay if cursor provided
                if since_cursor is not None:
                    replay_events = session.get_events_since(since_cursor)
                    logger.info(f"Replaying {len(replay_events)} events since cursor {since_cursor}")
                return session, replay_events
        
        # Create new session if not found
        session = self.create_session(agent_id, client_id, session_id)
        return session, []
    
    def on_event(self, event_type: str) -> Callable:
        """Decorator to register an event handler."""
        def decorator(func: Callable) -> Callable:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(func)
            return func
        return decorator
    
    def _client_has_scope(self, client_id: str, scope: OperatorScope) -> bool:
        """Whether a connected client holds ``scope`` (ADMIN implies all).

        Clients connected before scopes were tracked, or when no scope policy
        is configured, hold all scopes — preserving prior behaviour.
        """
        scopes = self._client_scopes.get(client_id)
        if scopes is None:
            return True
        return OperatorScope.ADMIN.value in scopes or scope.value in scopes

    @staticmethod
    def _event_required_scope(event: GatewayEvent) -> OperatorScope:
        """Map an outbound event class to the scope required to receive it.

        Approval-class events are only delivered to clients holding the
        ``approvals`` scope; everything else is visible with ``read``.
        """
        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
        if "approval" in event_type:
            return OperatorScope.APPROVALS
        return OperatorScope.READ

    def _event_visible_to(self, event: GatewayEvent, client_id: str) -> bool:
        """Whether ``event`` should be delivered to ``client_id`` given its scopes."""
        return self._client_has_scope(client_id, self._event_required_scope(event))

    async def emit(self, event: GatewayEvent) -> None:
        """Emit an event to registered handlers."""
        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
    
    async def broadcast(
        self,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> None:
        """Broadcast an event to all connected clients.

        Outbound events are filtered by each subscriber's operator scopes so a
        low-privilege (``read``-only) client never receives, for example,
        approval-request events it cannot act on. When no scope policy is
        configured every client holds all scopes, so behaviour is unchanged.
        """
        exclude_set = set(exclude or [])
        data = event.to_dict()

        # Per-connection send isolation: offer to each client's bounded queue
        # so one slow/stalled consumer cannot head-of-line block delivery to
        # healthy clients. Clients whose buffer is exhausted are collected and
        # evicted with a typed SLOW_CONSUMER reason after the fan-out.
        slow: List[str] = []
        for client_id, ws in list(self._clients.items()):
            if client_id in exclude_set or not self._event_visible_to(event, client_id):
                continue
            conn = self._client_conns.get(client_id)
            if conn is not None:
                # Queue a per-client snapshot so a later mutation of ``data``
                # cannot alter frames already buffered for other clients.
                if not conn.offer(dict(data)):
                    slow.append(client_id)
            else:
                # Compatibility fallback for directly-registered clients.
                try:
                    await ws.send_json(data)
                except Exception as e:
                    logger.error(f"Broadcast error to {client_id}: {e}")

        for client_id in slow:
            await self._evict_slow_consumer(client_id)
    
    # ── Message-flow metrics ──────────────────────────────────────────
    def record_metric(
        self,
        name: str,
        amount: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a message-flow counter (no-op when metrics unavailable).

        Public hook so bot adapters / supervision can emit flow counters such
        as ``messages_inbound_total`` or ``outbound_failed_total`` that surface
        on ``GET /metrics``. Safe to call from any thread.
        """
        if self._metrics is None:
            return
        try:
            self._metrics.inc(name, amount, labels=labels)
        except Exception as e:  # pragma: no cover — metrics must never break flow
            logger.debug("record_metric failed for %s: %s", name, e)

    def _refresh_metric_gauges(self) -> None:
        """Sample live gauges (sessions, supervision error/restart counts).

        Called lazily on each ``/metrics`` scrape so derived gauges/counters
        reflect current state without a polling loop. Best-effort: any failure
        is swallowed so a scrape never errors the gateway.
        """
        if self._metrics is None:
            return
        try:
            self._metrics.set_gauge("active_sessions", float(len(self._sessions)))
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("metric gauge refresh failed: %s", e)
        # Mirror supervision counters so per-channel error/restart rates are
        # visible even though supervision tracks them on its own status objects.
        try:
            for name, status in self._channel_supervisor.get_all_status().items():
                recoveries = getattr(status, "total_recoveries", 0) or 0
                self._metrics.set_gauge(
                    "channel_recoveries", float(recoveries),
                    labels={"channel": name},
                )
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("supervision metric mirror failed: %s", e)

    def metrics_snapshot(self) -> Dict[str, Any]:
        """Return a plain-dict snapshot of current metrics (for JSON/tests)."""
        if self._metrics is None:
            return {}
        self._refresh_metric_gauges()
        return self._metrics.snapshot()

    def health(self) -> Dict[str, Any]:
        """Get gateway health status including per-channel bot status and supervision state."""
        uptime = time.time() - self._started_at if self._started_at else 0
        channel_status = {}
        supervision_status = self._channel_supervisor.get_all_status()
        
        for name, bot in self._channel_bots.items():
            running = getattr(bot, "is_running", False)
            platform = getattr(bot, "platform", "unknown")
            
            # Get supervision state
            sup_status = supervision_status.get(name)
            if sup_status:
                channel_status[name] = {
                    "platform": platform,
                    "running": running,
                    "supervision": {
                        "state": sup_status.state.value,
                        "last_error": sup_status.last_error,
                        "last_error_time": sup_status.last_error_time,
                        "next_retry_at": sup_status.next_retry_at,
                        "total_recoveries": sup_status.total_recoveries,
                        "manual_pause": sup_status.manual_pause,
                    }
                }
            else:
                channel_status[name] = {
                    "platform": platform,
                    "running": running,
                }
                
        result = {
            "status": "healthy" if self._is_running else "stopped",
            "uptime": uptime,
            "agents": len(self._agents),
            "sessions": len(self._sessions),
            "clients": len(self._clients),
            "channels": channel_status,
        }

        # Issue #3021: surface opt-in lifecycle state so an operator can see
        # whether scale-to-zero is armed / the gateway is dormant / an external
        # drain watcher is active — without scraping logs. Only included when a
        # lifecycle feature is configured, so always-on gateways are unchanged.
        if self._idle_policy is not None or self._drain_marker_policy is not None:
            result["lifecycle"] = {
                "scale_to_zero": self._idle_policy is not None,
                "dormant": self._is_dormant,
                "drain_marker_watch": self._drain_marker_policy is not None,
            }

        # Issue #3049: surface config hot-reload observability so an operator
        # can see the last reload outcome, whether the watcher is alive, and
        # whether the config on disk actually took effect (drift detection) —
        # without restarting or scraping logs. Only included when running from
        # a config file, and computed defensively so health() never raises.
        reload_status = self._reload_status
        if reload_status is None and self._config_path is not None:
            # Watcher armed but no reload attempted yet this run.
            reload_status = ReloadStatus(
                watcher="active" if self._reload_watcher_active else "disabled",
            )
        if reload_status is not None:
            reload_data = reload_status.to_dict()
            # The ``watcher`` field on ``_reload_status`` is a snapshot taken at
            # record time; overlay the *live* liveness flag so a watcher that
            # exited after the last reload is reported as ``disabled`` rather
            # than stale ``active`` — the failure this surface exists to expose.
            reload_data["watcher"] = (
                "active" if self._reload_watcher_active else "disabled"
            )
            result["reload"] = reload_data
        if self._applied_config_revision is not None:
            result["applied_config_revision"] = self._applied_config_revision
        if self._config_path is not None:
            try:
                on_disk = compute_config_revision(
                    self.load_gateway_config(self._config_path)
                )
            except Exception:
                on_disk = None
            if on_disk is not None:
                result["on_disk_config_revision"] = on_disk
                if self._applied_config_revision is not None:
                    result["config_drift"] = (
                        on_disk != self._applied_config_revision
                    )
        
        # Add push status if enabled (push infra lives in wrapper; guard defensively)
        if getattr(self, "_push_enabled", False):
            push_status: Dict[str, Any] = {"enabled": True}
            channel_mgr = getattr(self, "_channel_mgr", None)
            if channel_mgr is not None:
                push_status["push_channels"] = len(channel_mgr.list_channels())
            presence_mgr = getattr(self, "_presence_mgr", None)
            if presence_mgr is not None:
                push_status["online_clients"] = presence_mgr.get_online_count()
            redis_pubsub = getattr(self, "_redis_pubsub", None)
            if redis_pubsub is not None:
                push_status["redis_connected"] = getattr(redis_pubsub, "_client", None) is not None
            result["push"] = push_status
        
        return result

    # ── Readiness / liveness probes ───────────────────────────────────

    def _unhealthy_channels(self) -> List[Tuple[str, Any]]:
        """Return [(name, status)] for channels in a FAILED supervision state.

        A channel that is paused/stopped is treated as not-blocking readiness;
        only FAILED channels (unrecoverable or actively erroring) are reported.
        """
        unhealthy: List[Tuple[str, Any]] = []
        try:
            from .supervisor import ChannelState
            for name, status in self._channel_supervisor.get_all_status().items():
                if status.state == ChannelState.FAILED:
                    unhealthy.append((name, status))
        except Exception as e:
            # Fail closed: if we cannot inspect supervision, surface it as a
            # readiness failure rather than silently reporting healthy.
            logger.warning("Readiness probe failed to inspect channel supervision: %s", e)
            unhealthy.append(("supervisor-error", None))
        return unhealthy

    async def _event_loop_responsive(self, threshold: float = 1.0) -> bool:
        """Measure event-loop responsiveness by timing a zero-delay sleep.

        If the loop is saturated/blocked, ``asyncio.sleep(0)`` takes much
        longer to be scheduled than wall-clock zero. A lag above ``threshold``
        seconds indicates the loop is not responsive.

        Args:
            threshold: Maximum acceptable scheduling lag in seconds.

        Returns:
            True if the loop scheduled the callback within ``threshold``.
        """
        try:
            loop = asyncio.get_running_loop()
            start = loop.time()
            await asyncio.sleep(0)
            lag = loop.time() - start
            return lag <= threshold
        except Exception as e:
            # Fail closed: an error sampling the loop means we cannot confirm
            # responsiveness, so report not-responsive.
            logger.warning("Liveness probe failed to sample event loop lag: %s", e)
            return False

    async def _readiness_failures(self) -> List[str]:
        """Return a list of reasons the gateway is not ready ([] when ready).

        - ``startup-pending`` while the gateway has not finished starting.
        - ``draining`` during graceful shutdown so LBs stop routing first.
        - ``event-loop`` when the asyncio loop is saturated/blocked.
        - ``channel:<name>`` for each channel in a FAILED supervision state.
        """
        failing: List[str] = []
        if self._draining:
            failing.append("draining")
        elif not self._is_running:
            failing.append("startup-pending")
        if not await self._event_loop_responsive():
            failing.append("event-loop")
        failing += [f"channel:{name}" for name, _ in self._unhealthy_channels()]
        return failing

    # ── Scheduled delivery ────────────────────────────────────────────

    async def _deliver_scheduled_result(
        self, delivery: Any, text: str,
    ) -> None:
        """Route a scheduled job result to the correct channel bot.

        Args:
            delivery: A ``DeliveryTarget`` with ``channel`` and ``channel_id``.
            text: The agent response to deliver.
        """
        channel = getattr(delivery, "channel", "") or ""
        channel_id = getattr(delivery, "channel_id", "") or ""
        thread_id = getattr(delivery, "thread_id", None)
        session_id = getattr(delivery, "session_id", None)

        if not channel or not channel_id:
            logger.warning("Delivery target missing channel or channel_id, skipping")
            return

        router = self.delivery_router
        if router is not None:
            # Route through the resilient router (issue #2624): token-bucket
            # throttle + LRU idempotency dedup + dead-target skip/self-heal.
            # ``session_id`` (``cron_<job.id>`` for scheduled runs) is folded
            # into the idempotency key so a crash-and-resume that re-fires the
            # same job result to the same target is deduplicated in-process.
            idem = (
                f"sched:{channel}:{channel_id}:{session_id or ''}:"
                f"{_delivery_text_digest(text)}"
            )
            # The router now preserves the thread segment end-to-end, so a
            # threaded delivery routes through the SHARED router directly (its
            # bounded LRU owns dedup, its token bucket throttles, its dead-target
            # registry suppresses/self-heals) — no thread-binding workaround.
            if thread_id is None:
                route = f"{channel}:{channel_id}"
            else:
                route = f"{channel}:{channel_id}:{thread_id}"
            delivered = await router.deliver(
                route, text, idempotency_key=idem,
            )
            if delivered:
                logger.info(
                    "Delivered scheduled result to %s:%s", channel, channel_id,
                )
            else:
                logger.error(
                    "Failed to deliver scheduled result to %s:%s", channel, channel_id,
                )
            return

        # Fallback: router unavailable — preserve the prior bare-send behaviour.
        bot = self.get_channel_bot(channel)
        if bot is None:
            # Try case-insensitive lookup
            for name, b in self._channel_bots.items():
                if name.lower() == channel.lower():
                    bot = b
                    break

        if bot is None:
            logger.warning(
                "No channel bot '%s' found for scheduled delivery", channel,
            )
            return

        try:
            await bot.send_message(
                channel_id, text, thread_id=thread_id,
            )
            logger.info(
                "Delivered scheduled result to %s:%s", channel, channel_id,
            )
        except Exception as e:
            logger.error(
                "Failed to deliver to %s:%s: %s", channel, channel_id, e,
            )

    def _start_scheduler_tick(self, interval: float = 15.0) -> None:
        """Start a background task that polls the scheduler for due jobs.

        Creates a ``ScheduledAgentExecutor`` wired to:
        - a ``ScheduleRunner`` with a ``FileScheduleStore``
        - this gateway's agent registry for resolution
        - ``_deliver_scheduled_result`` for outbound delivery
        """
        async def _run():
            try:
                from praisonaiagents.scheduler import (
                    ScheduleRunner,
                    FileScheduleStore,
                )
                from praisonai_bot.scheduler.executor import ScheduledAgentExecutor
            except ImportError as e:
                logger.warning(
                    "Scheduler dependencies not available, skipping tick: %s", e,
                )
                return

            store = FileScheduleStore()
            runner = ScheduleRunner(store)

            def _resolve_agent(agent_id):
                if agent_id:
                    return self._agents.get(agent_id)
                # Fallback: first registered agent
                return next(iter(self._agents.values()), None) if self._agents else None

            executor = ScheduledAgentExecutor(
                runner=runner,
                agent_resolver=_resolve_agent,
                delivery_handler=self._deliver_scheduled_result,
            )
            await executor.run_loop(interval=interval)

        self._scheduler_task = asyncio.create_task(_run())
        logger.info("Scheduler tick started (interval=15s)")
    
    async def _start_session_cleanup(self) -> None:
        """Start periodic cleanup of expired sessions."""
        if not self._session_store:
            return  # No cleanup needed without persistence
        
        async def _cleanup():
            while self._is_running:
                try:
                    await asyncio.sleep(3600)  # Check hourly
                    
                    # Clean up expired session TTLs
                    current_time = time.time()
                    expired_sessions = [
                        sid for sid, expiry in self._session_ttls.items()
                        if expiry < current_time
                    ]
                    
                    for sid in expired_sessions:
                        try:
                            # Remove from TTL tracking
                            self._session_ttls.pop(sid, None)
                            
                            # Delete from persistent store
                            if self._session_store:
                                self._session_store.delete_session(sid)
                                logger.info(f"Expired session removed from store: {sid}")
                        except Exception as e:
                            logger.warning(f"Failed to cleanup expired session {sid}: {e}")
                            
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")
        
        self._cleanup_task = asyncio.create_task(_cleanup())
        logger.info("Session cleanup task started (interval=1h)")

    # ── Multi-bot lifecycle ───────────────────────────────────────────

    @staticmethod
    def _substitute_env_vars(value: str) -> str:
        """Replace ``${VAR_NAME}`` patterns with environment variable values.

        Previously, missing env vars returned the literal ``${VAR_NAME}`` which
        caused downstream APIs (e.g. Telegram) to receive a broken token
        string and fail with opaque 404s. We now substitute missing vars with
        an **empty string** so the schema validator's required-field checks
        (e.g. ``token`` must be truthy) trip cleanly instead.
        """
        if not isinstance(value, str):
            return value
        def _replacer(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                logger.warning(
                    f"Environment variable {var_name} not set "
                    f"— substituting empty string. "
                    f"Run `praisonai onboard` or set it in ~/.praisonai/.env."
                )
                return ""
            return env_val
        return re.sub(r'\$\{([^}]+)\}', _replacer, value)

    @classmethod
    def load_gateway_config(cls, config_path: str) -> Dict[str, Any]:
        """Load and parse a gateway.yaml configuration file.

        Performs environment variable substitution on all string values.

        Args:
            config_path: Path to the YAML configuration file.

        Returns:
            Parsed configuration dictionary with env vars resolved.
        """
        import yaml

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Gateway config not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw or not isinstance(raw, dict):
            raise ValueError(f"Invalid gateway config: {config_path}")

        # ── Canonical schema validation (issue #3018) ──────────────
        # Route through the single, registry-aware validator that the ``bot``
        # CLI already uses instead of a second hand-rolled allowlist. This
        # migrates legacy config shapes (single-bot / BotOS / string
        # allowed_users) and *fails closed* on an unknown/typo'd platform
        # rather than emitting a warning and starting a channel that will
        # silently never run. Validation reads the platform registry
        # (built-ins + entry-point-discovered + ``register_platform()``), so
        # plugin channels validate on the runtime path too. Unknown-platform
        # and missing-token failures raise ``ValueError`` here, which the CLI
        # maps to the fatal-config exit code (78) so supervisors don't
        # crash-loop.
        from praisonai_bot.bots._config_schema import (
            migrate_legacy_config,
            validate_gateway_config,
        )

        def _resolve(obj):
            if isinstance(obj, str):
                return cls._substitute_env_vars(obj)
            if isinstance(obj, dict):
                return {k: _resolve(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_resolve(v) for v in obj]
            return obj

        migrated = migrate_legacy_config(raw)

        # ── Gateway-runtime required-section contract ──────────────
        # The canonical schema treats ``agent``/``agents`` and per-channel
        # ``token`` as optional (it serves the ``bot`` CLI's looser shapes).
        # The gateway *runtime*, however, needs an ``agents`` map to build
        # agents from, a ``channels`` map to start adapters, and a token per
        # channel (except tokenless platforms). Enforce those here — on the
        # *pre-substitution* config so a channel with **no** ``token`` key
        # fails closed, while a ``${VAR}`` that resolves to empty is left for
        # ``start_channels()`` to skip (regression guard, PR #3019 review).
        # Platform/typo fail-closed is still delegated to the canonical
        # validator below (single source of truth for the registry).
        errors: list[str] = []
        agents_cfg = migrated.get("agents")
        if not agents_cfg:
            errors.append("Missing required 'agents' section")
        elif not isinstance(agents_cfg, dict):
            errors.append("'agents' must be a non-empty dictionary")

        channels_cfg = migrated.get("channels")
        if not channels_cfg:
            errors.append("Missing required 'channels' section")
        elif not isinstance(channels_cfg, dict):
            errors.append("'channels' must be a non-empty dictionary")
        else:
            _tokenless = {"email", "agentmail"}
            for cname, cdef in channels_cfg.items():
                if not isinstance(cdef, dict):
                    continue
                platform = str(cdef.get("platform", cname)).lower()
                is_wa_web = (
                    platform == "whatsapp"
                    and str(cdef.get("mode", cdef.get("whatsapp_mode", "cloud")))
                    .lower()
                    .strip()
                    == "web"
                )
                if (
                    "token" not in cdef
                    and platform not in _tokenless
                    and not is_wa_web
                ):
                    errors.append(
                        f"Channel '{cname}' missing 'token' "
                        "(use ${ENV_VAR} syntax for env vars)"
                    )

        if errors:
            raise ValueError(
                f"Gateway config validation failed ({config_path}):\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        # Resolve ``${VAR}`` *before* validation so the schema sees literal
        # values, not placeholders. This loader owns env resolution and maps an
        # unset var to an empty string (``_substitute_env_vars``); doing it up
        # front means an unset token for a currently-unused channel stays an
        # empty string that ``start_channels()`` skips, instead of tripping the
        # schema's ``${VAR}``-token validator and aborting the whole gateway
        # (regression guard, PR #3019 review). Platform-typo fail-closed still
        # applies — that check keys off the platform *name*, not the token.
        raw = _resolve(migrated)
        # Validate (raises ValueError on unknown platform / no channels). Env
        # substitution already happened above, so skip the schema's own.
        validated = validate_gateway_config(raw, apply_env_substitution=False)
        # The schema normalises legacy single-bot (top-level platform/token)
        # and BotOS (``platforms:``) shapes into a ``channels`` dict, resolves
        # the effective ``platform`` name, and wires plugin descriptor env
        # fallbacks / required fields (Issue #2801). Merge those validated
        # channel fields back so the runtime — which reads ``channels`` from
        # this dict — starts adapters with the same fully-resolved settings the
        # ``bot`` command sees. User-supplied raw values win; validator-derived
        # fields only fill gaps (PR #3019 review: existing ``channels:`` configs
        # previously lost descriptor-populated fields).
        if validated.channels:
            raw_channels = raw.get("channels")
            if not isinstance(raw_channels, dict):
                raw_channels = {}
            # Credential fields the schema resolves from a secret-reference form
            # (Issue #3102). When the raw value is a ``{source, id}`` reference,
            # the validator has already resolved it to a plaintext string; that
            # resolved value must win so the adapter never receives the raw,
            # unresolved dict (which would e.g. break WhatsApp verify_token).
            _secret_fields = ("token", "app_token", "verify_token")
            merged: Dict[str, Any] = {}
            for name, channel in validated.channels.items():
                validated_fields = channel.model_dump(exclude_none=True)
                existing = raw_channels.get(name)
                if isinstance(existing, dict):
                    merged[name] = {**validated_fields, **existing}
                    for key, val in validated_fields.items():
                        if existing.get(key) in (None, ""):
                            merged[name][key] = val
                        # A resolved secret string always wins over a raw
                        # secret-reference dict so adapters get the value.
                        elif (
                            key in _secret_fields
                            and isinstance(existing.get(key), dict)
                        ):
                            merged[name][key] = val
                else:
                    merged[name] = validated_fields
            raw["channels"] = merged

        return raw

    def _create_agents_from_config(
        self,
        agents_cfg: Dict[str, Dict[str, Any]],
        *,
        default_model: Optional[str] = None,
        guardrails_cfg: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create and register Agent instances from the agents section of config.

        Supports all agent configuration options including:
        - tools: List of tool names to resolve via ToolResolver
        - tool_choice: Tool selection mode ('auto', 'required', 'none')
        - reflection: Enable reflection/interactive mode (default: False)
        - allow_delegation: Allow task delegation
        - role: Agent role (CrewAI-style)
        - goal: Agent goal (CrewAI-style)
        - backstory: Agent backstory (CrewAI-style)
        - temperature: LLM temperature (optional, uses SDK default)
        - base_url: Custom LLM endpoint URL (optional)
        - api_key: API key for LLM provider (optional)

        Args:
            agents_cfg: The ``agents`` section of the config.
            default_model: Fallback model when an agent has no ``model`` key
                           (e.g. from the ``provider.model`` section of UI config).
            guardrails_cfg: Optional ``guardrails.registry`` dict to wire per-agent.
        """
        from praisonaiagents import Agent

        # Resolve tool names to callables (same pattern as agents_generator)
        tool_resolver = None
        try:
            from praisonai_bot._code_bridge import import_code_module

            ToolResolver = import_code_module("praisonai_code.tool_resolver").ToolResolver
            tool_resolver = ToolResolver()
        except ImportError:
            logger.debug("ToolResolver not available, agents will have no tools")

        for agent_id, agent_def in agents_cfg.items():
            instructions = agent_def.get("instructions", "")
            # G7: Apply provider.model as fallback when agent has no model
            model = agent_def.get("model", None) or default_model
            memory = agent_def.get("memory", False)

            # G2: Pass temperature through (optional, SDK uses its own default)
            temperature = agent_def.get("temperature", None)
            # G3/G4: Pass base_url and api_key for multi-provider support
            base_url = agent_def.get("base_url", None)
            api_key = agent_def.get("api_key", None)

            # Support role/goal/backstory for CrewAI-style agents
            role = agent_def.get("role", None)
            goal = agent_def.get("goal", None)
            backstory = agent_def.get("backstory", None)

            # G6: Fall back to system_prompt if instructions is empty
            if not instructions:
                instructions = agent_def.get("system_prompt", "") or ""

            # Resolve tools from YAML config
            # Track if tools key was explicitly set (even as empty list) vs omitted
            tools_key_present = "tools" in agent_def
            explicit_empty_tools = tools_key_present and not agent_def.get("tools")
            
            agent_tools = []
            yaml_tool_names = agent_def.get("tools", [])
            if yaml_tool_names and tool_resolver:
                for tool_name in yaml_tool_names:
                    if not tool_name or not isinstance(tool_name, str):
                        continue
                    tool_name = tool_name.strip()
                    resolved = tool_resolver.resolve(tool_name)
                    if resolved:
                        agent_tools.append(resolved)
                        logger.debug(f"Resolved tool '{tool_name}' for agent '{agent_id}'")
                    else:
                        logger.warning(f"Tool '{tool_name}' not found for agent '{agent_id}'")

            # Additional agent options from YAML.
            tool_choice = agent_def.get("tool_choice", None)
            
            # reflection defaults to False for gateway agents: chat channels
            # (Telegram/Discord/Slack/WhatsApp) expect sub-second replies, and
            # self-reflection adds 1-N extra LLM round-trips per message
            # (~8x latency for short prompts on gpt-4o-mini). Users who want
            # higher answer quality can opt in with `reflection: true` in YAML.
            reflection = agent_def.get("reflection", False)
            allow_delegation = agent_def.get("allow_delegation", False)

            # G5: Wire guardrails if config has a matching agent_name or global rule
            guardrail_prompt = None
            if guardrails_cfg:
                for _gr_id, gr_def in guardrails_cfg.items():
                    gr_agent = gr_def.get("agent_name", "")
                    if not gr_agent or gr_agent == agent_id:
                        guardrail_prompt = gr_def.get("description", None)
                        break  # first match wins

            # Compose model as dict when temperature is specified
            # (Agent accepts temperature via dict model config)
            model_cfg = model
            if temperature is not None and model and isinstance(model, str):
                model_cfg = {"model": model, "temperature": temperature}

            # Use model= (preferred) instead of deprecated llm=
            agent = Agent(
                name=agent_id,
                instructions=instructions,
                model=model_cfg,
                memory=memory,
                tools=agent_tools if agent_tools else None,
                reflection=reflection,
                allow_delegation=allow_delegation,
                role=role,
                goal=goal,
                backstory=backstory,
                base_url=base_url,
                api_key=api_key,
                guardrails=guardrail_prompt,
            )

            # Store tool_choice for later use in chat()
            if tool_choice:
                agent._yaml_tool_choice = tool_choice
            
            # Store explicit empty tools flag to prevent smart defaults injection
            if explicit_empty_tools:
                agent._explicit_empty_tools = True

            self.register_agent(agent, agent_id=agent_id)
            logger.info(
                f"Created agent '{agent_id}' "
                f"(model={model}, tools={len(agent_tools)}, "
                f"reflection={reflection})"
            )

    def _determine_routing_context(
        self, channel_type: str, message_metadata: Dict[str, Any]
    ) -> str:
        """Determine the routing context key for a message.

        Args:
            channel_type: Platform name (telegram, discord, slack).
            message_metadata: Dict with at least 'chat_type' or 'is_dm' keys.

        Returns:
            Context string: 'dm', 'group', 'channel', or 'default'.
        """
        chat_type = message_metadata.get("chat_type", "")
        is_dm = message_metadata.get("is_dm", False)

        if is_dm or chat_type in ("private", "dm"):
            return "dm"
        if chat_type in ("group", "supergroup", "guild"):
            return "group"
        if chat_type == "channel":
            return "channel"
        return "default"

    def _resolve_agent_for_message(
        self,
        channel_name: str,
        context: str,
        facts: Optional[Any] = None,
    ) -> Optional["Agent"]:
        """Look up the correct agent for a channel + context.

        Resolution order (Issue #2225):
          1. Priority-ordered ``bindings`` (peer / role / channel_id / account /
             chat_type) evaluated most-specific-first, when ``facts`` is given.
          2. Flat ``routes`` map keyed by chat-type context (legacy behaviour).
          3. The ``default`` agent.

        Args:
            channel_name: The channel/platform name.
            context: Chat-type context token ('dm' | 'group' | 'channel' | 'default').
            facts: Optional :class:`RouteFacts` carrying richer inbound facts
                (sender id, roles, channel id, account). When omitted, only the
                flat chat-type routes are consulted.

        Returns:
            The resolved Agent, or None if it cannot be found.
        """
        rules = self._routing_rules.get(channel_name, {})
        default_agent_id = rules.get("default", "default")

        agent_id = None
        bindings = self._routing_bindings.get(channel_name) or []
        if bindings and facts is not None:
            try:
                from praisonaiagents.gateway import resolve_route

                match = resolve_route(bindings, facts, default_agent=default_agent_id)
                if match.binding is not None:
                    agent_id = match.agent
                    logger.debug(
                        f"Routing channel={channel_name} -> agent='{agent_id}' "
                        f"({match.reason})"
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"Binding resolution failed for {channel_name}: {exc}")

        if agent_id is None:
            agent_id = rules.get(context) or default_agent_id

        agent = self._agents.get(agent_id)
        if not agent:
            logger.warning(
                f"No agent '{agent_id}' for channel={channel_name} context={context}"
            )
        return agent

    def _resolve_tool_policy_for_message(
        self,
        channel_name: str,
        facts: Optional[Any] = None,
    ) -> Optional[Any]:
        """Resolve the per-route toolset scope for an inbound message (Issue #2298).

        Returns the :class:`ToolPolicy` declared by the matching route binding
        (via ``trust`` / ``allow_tools`` / ``deny_tools``), or ``None`` when no
        binding matched or the matched binding does not constrain the toolset.
        Down-scoping untrusted routes here means dangerous tools are never even
        advertised to the model, shrinking the prompt-injection attack surface.
        """
        if facts is None:
            return None
        bindings = self._routing_bindings.get(channel_name) or []
        if not bindings:
            return None
        try:
            from praisonaiagents.gateway import resolve_route

            match = resolve_route(bindings, facts)
            binding = getattr(match, "binding", None)
            if binding is None:
                return None
            tool_policy = getattr(binding, "tool_policy", None)
            return tool_policy() if callable(tool_policy) else None
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                f"Tool-policy resolution failed for {channel_name}: {exc}"
            )
            return None

    @staticmethod
    def _build_route_facts(
        chat_type: str,
        *,
        peer: Optional[str] = None,
        roles: Optional[List[str]] = None,
        channel_id: Optional[str] = None,
        account: Optional[str] = None,
    ) -> Any:
        """Build a RouteFacts object from inbound message facts.

        Returns None if the core RouteFacts type is unavailable so callers can
        gracefully fall back to chat-type-only routing.
        """
        try:
            from praisonaiagents.gateway import RouteFacts

            return RouteFacts(
                chat_type=chat_type or "default",
                peer=str(peer) if peer is not None else None,
                roles=list(roles or []),
                channel_id=str(channel_id) if channel_id is not None else None,
                account=str(account) if account is not None else None,
            )
        except Exception:  # pragma: no cover - defensive
            return None

    @staticmethod
    def _parse_bindings(raw: Any) -> List[Any]:
        """Parse a list of route-binding dicts into RouteBinding objects.

        Returns an empty list for missing/invalid input so routing falls back
        to the flat ``routes`` map.
        """
        if not raw or not isinstance(raw, list):
            return []
        try:
            from praisonaiagents.gateway import RouteBinding
        except Exception:  # pragma: no cover - defensive
            return []
        bindings: List[Any] = []
        for item in raw:
            if not isinstance(item, dict):
                logger.warning("Ignoring non-mapping route binding: %r", item)
                continue
            if not item.get("agent"):
                logger.warning(
                    "Ignoring route binding without an 'agent' key: %r", item
                )
                continue
            try:
                bindings.append(RouteBinding.from_dict(item))
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Ignoring invalid route binding %r: %s. "
                    "Fix the binding shape or priority value and retry.",
                    item,
                    exc,
                )
        return bindings

    async def start_channels(self, channels_cfg: Dict[str, Dict[str, Any]]) -> None:
        """Start bot instances for each configured channel.

        Each bot runs as a concurrent asyncio task.  If a single bot fails
        to start the others continue running.

        Args:
            channels_cfg: The ``channels`` section of gateway.yaml.
        """
        from praisonaiagents.bots import BotConfig

        for channel_name, ch_cfg in channels_cfg.items():
            channel_type = ch_cfg.get("platform", channel_name).lower()
            token = ch_cfg.get("token", "")
            # WhatsApp web mode doesn't require a token
            wa_web_mode = (channel_type == "whatsapp" and
                           ch_cfg.get("mode", "cloud").lower().strip() == "web")
            # Email/AgentMail use env vars for tokens — not required in YAML
            is_email_platform = channel_type in ("email", "agentmail")
            if not token and not wa_web_mode and not is_email_platform:
                logger.warning(f"No token for channel '{channel_name}', skipping")
                continue

            routes = ch_cfg.get("routing") or ch_cfg.get("routes") or {"default": "default"}
            self._routing_rules[channel_name] = routes
            self._routing_bindings[channel_name] = self._parse_bindings(
                ch_cfg.get("bindings")
            )

            # Resolve default agent for this channel (used as the bot's primary agent)
            default_agent_id = routes.get("default", next(iter(self._agents.keys())) if self._agents else "default")
            default_agent = self._agents.get(default_agent_id)
            if not default_agent:
                logger.warning(f"Default agent '{default_agent_id}' not found for channel '{channel_name}', skipping")
                continue

            # Extract allowlist configuration from channel config  
            _raw_allowed = ch_cfg.get("allowed_users") or []
            if isinstance(_raw_allowed, str):
                # Env-expanded string like "12345,67890"; split on commas.
                _raw_allowed = [s.strip() for s in _raw_allowed.split(",") if s.strip()]

            _raw_channels = ch_cfg.get("allowed_channels") or []
            if isinstance(_raw_channels, str):
                _raw_channels = [s.strip() for s in _raw_channels.split(",") if s.strip()]

            # Extract group policy setting
            group_policy = ch_cfg.get("group_policy", "mention_only")
            mention_required = (group_policy == "mention_only")

            # Extract auto_approve_tools setting (default True for chat bots)
            _raw_auto_approve = ch_cfg.get("auto_approve_tools")
            if _raw_auto_approve is None:
                auto_approve_tools = True   # SAFE-DEFAULT: safe tools auto-approved in chat
            elif isinstance(_raw_auto_approve, str):
                auto_approve_tools = _raw_auto_approve.strip().lower() in ("1", "true", "yes", "on")
            else:
                auto_approve_tools = bool(_raw_auto_approve)

            config_kwargs = dict(
                token=token,
                allowed_users=list(_raw_allowed),
                allowed_channels=list(_raw_channels),
                mention_required=mention_required,
                group_policy=group_policy,
                auto_approve_tools=auto_approve_tools,
            )

            # Issue #2855: wire the inbound admission policy from gateway.yaml so
            # operators can open DMs (``allow``), enable pairing (``pair``), or
            # keep the secure default (``deny``). Without this, an empty
            # allowlist silently drops unknown users regardless of YAML.
            _raw_uup = ch_cfg.get("unknown_user_policy")
            if isinstance(_raw_uup, str) and _raw_uup.strip():
                config_kwargs["unknown_user_policy"] = _raw_uup.strip().lower()
            _raw_owner = ch_cfg.get("owner_user_id")
            if _raw_owner is not None and str(_raw_owner).strip():
                config_kwargs["owner_user_id"] = str(_raw_owner).strip()

            # Only pass default_tools when the channel explicitly overrides it,
            # so BotConfig's own default_factory stays the single source of truth.
            _raw_yaml_tools = ch_cfg.get("default_tools")
            if isinstance(_raw_yaml_tools, list):
                config_kwargs["default_tools"] = _raw_yaml_tools
            
            config = BotConfig(**config_kwargs)

            # Carry the inbound STT policy (Issue #2721) through the config's
            # metadata passthrough (BotConfig has no native ``stt`` field),
            # mirroring how ``max_inbound_media_bytes`` flows. On by default so
            # voice notes are transcribed out of the box; ``stt.enabled: false``
            # opts out. A bare ``stt: true/false`` shorthand is also accepted.
            _raw_stt = ch_cfg.get("stt")
            if _raw_stt is not None:
                try:
                    config.metadata["stt"] = _raw_stt
                except Exception:  # pragma: no cover — defensive
                    pass

            # Warn if no allowlist is configured. Issue #2855: the message must
            # reflect the effective ``unknown_user_policy`` — an empty allowlist
            # with the default ``deny`` policy SILENTLY DROPS unknown DMs, so the
            # old "accepts messages from everyone" text was misleading.
            if not config.allowed_users:
                self._warn_empty_allowlist(channel_name, config.unknown_user_policy)

            try:
                bot = self._create_bot(channel_type, token, default_agent, config, ch_cfg)
                if bot is None:
                    continue
                # Issue #2721: enable inbound speech-to-text so voice notes are
                # transcribed and fed to the agent. On by default; the resolved
                # policy (config.metadata["stt"]) drives the opt-out.
                self._enable_stt(bot, config)
                # Issue #2454: share the gateway-wide admission gate with this
                # channel bot so inbound runs are admitted through the global
                # concurrency ceiling / fair queue. No-op when not configured.
                self._stamp_admission_gate(bot)
                # Issue #3020: stamp the shared cross-platform identity resolver
                # so this channel keys sessions by canonical identity (unified
                # user) instead of a per-platform key. No-op when unconfigured.
                self._stamp_identity_resolver(bot)
                self._channel_bots[channel_name] = bot
                logger.info(f"Channel '{channel_name}' ({channel_type}) initialized")
            except Exception as e:
                logger.error(f"Failed to create bot for '{channel_name}': {e}")
                continue

        # Start all bots concurrently
        if self._channel_bots:
            # Start health monitoring if configured
            if self._health_config and self._health_config.enabled:
                await self._channel_supervisor.start_health_monitoring()
                logger.info("Channel health monitoring enabled")
            
            for name, bot in self._channel_bots.items():
                task = asyncio.create_task(self._run_bot_safe(name, bot))
                self._channel_tasks[name] = task
            logger.info(f"Started {len(self._channel_bots)} channel bot(s)")

    @staticmethod
    def _warn_empty_allowlist(channel_name: str, unknown_user_policy: str) -> None:
        """Emit an accurate startup warning for an empty ``allowed_users``.

        Issue #2855: the previous "accepts messages from everyone" text was
        misleading because the default ``unknown_user_policy=deny`` SILENTLY
        DROPS inbound DMs from unpaired/unknown users. The warning now reflects
        the effective policy so operators aren't left debugging a "broken" bot.
        """
        policy = (unknown_user_policy or "deny").lower()
        if policy == "allow":
            logger.warning(
                "Channel %r has no allowed_users and unknown_user_policy=allow "
                "— bot accepts messages from everyone.",
                channel_name,
            )
        elif policy == "pair":
            logger.warning(
                "Channel %r has no allowed_users and unknown_user_policy=pair "
                "— unknown users will be routed through the pairing flow.",
                channel_name,
            )
        else:  # deny (default)
            logger.warning(
                "Channel %r has no allowed_users and unknown_user_policy=deny "
                "— inbound messages from unpaired users will be SILENTLY DROPPED. "
                "Set allowed_users, configure pairing (unknown_user_policy: pair), "
                "or open DMs (unknown_user_policy: allow). "
                "Re-run `praisonai onboard` to configure.",
                channel_name,
            )

    def _enable_stt(self, bot: Any, config: Any) -> None:
        """Enable inbound speech-to-text on a channel bot (Issue #2721).

        Voice notes are transcribed and fed to the agent by default. The
        resolved policy is read from ``config.metadata["stt"]`` so an operator
        can opt out with ``stt.enabled: false``. No-op for adapters that don't
        expose ``enable_stt`` (e.g. email), preserving today's behaviour.
        """
        enable = getattr(bot, "enable_stt", None)
        if not callable(enable):
            return
        try:
            from praisonai_bot.bots._stt import resolve_stt_config
            stt = resolve_stt_config(config)
            enable(stt.enabled)
        except Exception as e:  # pragma: no cover — defensive
            logger.debug("Failed to configure STT for bot: %s", e, exc_info=True)

    def _stamp_admission_gate(self, bot: Any) -> None:
        """Share the gateway-wide admission gate with a channel bot (Issue #2454).

        The concrete adapters (TelegramBot, DiscordBot, …) expose their session
        under ``_session`` / ``_session_mgr``. No-op when admission control is
        not configured, preserving today's immediate-dispatch path. Called from
        both ``start_channels`` and ``_start_single_channel`` (hot-reload) so a
        restarted channel can't silently bypass the global concurrency ceiling.
        """
        gate = getattr(self, "_admission_gate", None)
        if gate is None:
            return
        sess = (
            getattr(bot, "_session", None)
            or getattr(bot, "_session_mgr", None)
        )
        if sess is not None and hasattr(sess, "_admission_gate"):
            sess._admission_gate = gate
        elif hasattr(bot, "_admission_gate"):
            bot._admission_gate = gate

    @staticmethod
    def _build_identity_resolver(identity_cfg: Any) -> Optional[Any]:
        """Build a cross-platform identity resolver from the ``identity:`` block.

        Issue #3020: turns the declarative ``gateway.yaml`` block into a live
        ``StoreBackedIdentityResolver`` so a paired/linked user shares one
        session + memory across channels out of the box::

            identity:
              enabled: true
              store: ~/.praisonai/identity.json   # optional link-map path

        Returns ``None`` (per-platform keys, today's behaviour) when the block
        is missing, not a mapping, or ``enabled`` is falsy. Any failure to
        build the resolver degrades gracefully to ``None`` rather than aborting
        gateway startup.
        """
        if not identity_cfg or not isinstance(identity_cfg, dict):
            return None
        enabled = identity_cfg.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return None
        store = identity_cfg.get("store") or identity_cfg.get("path")
        store = os.path.expanduser(str(store)) if store else None
        try:
            from ..bots import StoreBackedIdentityResolver

            resolver = StoreBackedIdentityResolver.from_env(path=store)
            logger.info(
                "Gateway cross-platform identity resolution enabled "
                "(store=%s)",
                store or "default",
            )
            return resolver
        except Exception as e:  # pragma: no cover - optional/degraded path
            logger.warning(
                "Gateway identity resolver unavailable, falling back to "
                "per-platform sessions: %s",
                e,
            )
            return None

    def _reconcile_identity_resolver(self, identity_cfg: Any) -> None:
        """Reconcile ``self._identity_resolver`` with the declarative block.

        Issue #3020: startup *and* hot-reload both route through here so a
        changed top-level ``identity:`` block actually takes effect. A changed
        block triggers a full channel restart (unknown reload section), and
        this must run *before* channels are recreated so freshly stamped bots
        pick up the new resolver instead of a stale one.

        Precedence: an explicit constructor/CLI resolver
        (``_identity_resolver_explicit``) always wins and is never rebuilt or
        cleared from YAML. Otherwise the resolver is rebuilt from the block —
        enabling it installs a resolver, disabling/removing it clears back to
        per-platform keys (today's default). Idempotent: an unchanged enabled
        block reuses the existing resolver so its in-memory link cache and
        store handle survive reloads that don't touch ``identity:``.
        """
        if getattr(self, "_identity_resolver_explicit", False):
            return
        built = self._build_identity_resolver(identity_cfg)
        # Preserve the live resolver across reloads that leave ``identity:``
        # semantically unchanged, so its link cache / store handle isn't churned.
        if (
            built is not None
            and self._identity_resolver is not None
            and self._identity_resolver_signature
            == self._signature_for_identity(identity_cfg)
        ):
            return
        self._identity_resolver = built
        self._identity_resolver_signature = (
            self._signature_for_identity(identity_cfg) if built is not None else None
        )

    @staticmethod
    def _signature_for_identity(identity_cfg: Any) -> Optional[Tuple[Any, ...]]:
        """Normalized (enabled, store) key used to detect ``identity:`` changes."""
        if not identity_cfg or not isinstance(identity_cfg, dict):
            return None
        enabled = identity_cfg.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        if not enabled:
            return None
        store = identity_cfg.get("store") or identity_cfg.get("path")
        store = os.path.expanduser(str(store)) if store else None
        return (True, store)

    def _stamp_identity_resolver(self, bot: Any) -> None:
        """Share the gateway's identity resolver with a channel bot (Issue #3020).

        Mirrors ``_stamp_admission_gate`` and the post-construction splice that
        ``Bot``/``BotOS`` already perform: the concrete adapters (TelegramBot,
        DiscordBot, …) build their own ``BotSessionManager`` during ``__init__``
        and expose it as ``_session`` / ``_session_mgr``. Stamping the resolver
        there makes ``BotSessionManager._storage_key`` key by the resolved
        canonical identity, so a paired/linked user shares one session + memory
        across every channel served by this gateway process.

        No-op when no resolver is configured, preserving today's per-platform
        session keys. Called from both ``start_channels`` and
        ``_start_single_channel`` (hot-reload) so a restarted channel keeps
        continuity too.
        """
        resolver = getattr(self, "_identity_resolver", None)
        if resolver is None:
            return
        sess = (
            getattr(bot, "_session", None)
            or getattr(bot, "_session_mgr", None)
        )
        if sess is not None and hasattr(sess, "_identity_resolver"):
            sess._identity_resolver = resolver
        elif hasattr(bot, "_identity_resolver"):
            bot._identity_resolver = resolver

    def _create_bot(
        self,
        channel_type: str,
        token: str,
        agent: "Agent",
        config: Any,
        ch_cfg: Dict[str, Any],
    ) -> Any:
        """Create a bot instance for the given channel type."""
        # Clone agent to prevent channel-specific settings from leaking between channels
        # Use clone_for_channel() instead of copy.deepcopy() to avoid RLock issues (fixes #1746)
        agent = agent.clone_for_channel()
        
        # Apply smart defaults to agent (same logic as Bot() wrapper)
        from praisonai_bot.bots._defaults import apply_bot_smart_defaults
        agent = apply_bot_smart_defaults(agent, config)

        # Check if agent ended up with zero tools after defaults and warn
        current_tools = getattr(agent, 'tools', None) or []
        if not current_tools:
            logger.warning(
                "Bot for channel %r started with zero tools — chat will be text-only. "
                "Check that `praisonaiagents.tools` is installed and that "
                "`tools: []` is not set explicitly in bot.yaml.",
                ch_cfg.get('platform', channel_type),
            )

        if channel_type == "telegram":
            from praisonai_bot.bots import TelegramBot
            return TelegramBot(token=token, agent=agent, config=config)
        elif channel_type == "discord":
            from praisonai_bot.bots import DiscordBot
            return DiscordBot(token=token, agent=agent, config=config)
        elif channel_type == "slack":
            from praisonai_bot.bots import SlackBot
            app_token = ch_cfg.get("app_token", os.environ.get("SLACK_APP_TOKEN", ""))
            return SlackBot(token=token, agent=agent, config=config, app_token=app_token)
        elif channel_type == "whatsapp":
            from praisonai_bot.bots import WhatsAppBot
            wa_mode = ch_cfg.get("mode", "cloud").lower().strip()
            return WhatsAppBot(
                token=token,
                phone_number_id=ch_cfg.get("phone_number_id", ""),
                agent=agent,
                config=config,
                verify_token=ch_cfg.get("verify_token", ""),
                webhook_port=int(ch_cfg.get("webhook_port", 8080)),
                mode=wa_mode,
                creds_dir=ch_cfg.get("creds_dir"),
            )
        elif channel_type == "linear":
            from praisonai_bot.bots import LinearBot
            linear_token = token or os.environ.get("LINEAR_OAUTH_TOKEN", "") or os.environ.get("LINEAR_API_KEY", "")
            return LinearBot(
                token=linear_token,
                agent=agent,
                config=config,
                signing_secret=ch_cfg.get("signing_secret", "") or os.environ.get("LINEAR_WEBHOOK_SECRET", ""),
                webhook_port=int(ch_cfg.get("webhook_port", 8080)),
            )
        elif channel_type == "email":
            from praisonai_bot.bots import EmailBot
            email_token = token or os.environ.get("EMAIL_APP_PASSWORD", "")
            return EmailBot(
                token=email_token,
                agent=agent,
                email_address=ch_cfg.get("email_address") or os.environ.get("EMAIL_ADDRESS", ""),
                imap_server=ch_cfg.get("imap_server") or os.environ.get("EMAIL_IMAP_SERVER", ""),
                smtp_server=ch_cfg.get("smtp_server") or os.environ.get("EMAIL_SMTP_SERVER", ""),
            )
        elif channel_type == "agentmail":
            from praisonai_bot.bots import AgentMailBot
            am_token = token or os.environ.get("AGENTMAIL_API_KEY", "")
            return AgentMailBot(
                token=am_token,
                agent=agent,
                inbox_id=ch_cfg.get("inbox_id") or os.environ.get("AGENTMAIL_INBOX_ID", ""),
                domain=ch_cfg.get("domain") or os.environ.get("AGENTMAIL_DOMAIN", ""),
            )
        else:
            logger.warning(f"Unknown channel type: {channel_type}")
            return None

    async def _run_bot_safe(self, name: str, bot: Any) -> None:
        """Run a single bot with supervision and resilient error handling.

        Uses the channel supervisor for unlimited retries with error classification,
        exponential backoff, and operator controls.
        """
        async def start_bot(name: str, bot: Any) -> None:
            """Start function for the supervisor."""
            # TelegramBot special handling: run_polling() tries to manage
            # its own event loop which conflicts with our gateway loop.
            # Use the lower-level API instead.
            if self._is_telegram_bot(bot):
                await self._start_telegram_bot_polling(name, bot)
            elif type(bot).__name__ in ("WhatsAppBot", "LinearBot"):
                # WhatsApp/Linear run their own aiohttp webhook servers
                self._inject_routing_handler(name, bot)
                await bot.start()
            else:
                # Inject routing-aware handler for Discord/Slack
                self._inject_routing_handler(name, bot)
                await bot.start()
        
        # Use supervisor for resilient channel management
        await self._channel_supervisor.run(name, bot, start_bot)

    @staticmethod
    def _is_telegram_bot(bot: Any) -> bool:
        """Check if a bot instance is a TelegramBot."""
        return type(bot).__name__ == "TelegramBot"

    def _inject_routing_handler(self, channel_name: str, bot: Any) -> None:
        """Inject a routing-aware on_message handler into a Discord/Slack bot.

        This overrides the bot's default agent with a dynamically-resolved
        agent based on the gateway's routing rules for each incoming message.
        """
        gateway = self

        @bot.on_message
        async def _routed_message_handler(message):
            if not message.sender:
                return
            # Determine routing context from channel type
            ch_type = message.channel.channel_type if message.channel else ""
            is_dm = ch_type in ("dm", "private")
            routing_ctx = gateway._determine_routing_context(
                channel_name, {"chat_type": ch_type, "is_dm": is_dm}
            )
            # Build richer facts for binding-based routing (Issue #2225)
            sender = message.sender
            peer = getattr(sender, "user_id", None) if sender else None
            roles = []
            sender_meta = getattr(sender, "metadata", None) if sender else None
            if isinstance(sender_meta, dict):
                raw_roles = sender_meta.get("roles")
                if isinstance(raw_roles, list):
                    roles = [str(r) for r in raw_roles]
            channel_id = getattr(message.channel, "channel_id", None) if message.channel else None
            bot_user = getattr(bot, "bot_user", None)
            account = getattr(bot_user, "user_id", None) if bot_user else None
            facts = gateway._build_route_facts(
                routing_ctx,
                peer=peer,
                roles=roles,
                channel_id=channel_id,
                account=account,
            )
            agent = gateway._resolve_agent_for_message(
                channel_name, routing_ctx, facts=facts
            )
            if agent:
                bot.set_agent(agent)
                # Per-route toolset scope (Issue #2298): the adapter's own
                # on_message calls ``_session.chat()`` without a tool_policy
                # arg, so stage the resolved policy on the session here — this
                # handler runs synchronously right before that chat() in the
                # same dispatch, so an untrusted Discord/Slack route never
                # advertises dangerous tools. ``None`` clears any prior staging
                # so a trusted route can't inherit an earlier untrusted scope.
                session = getattr(bot, "_session", None)
                if session is None:
                    adapter = getattr(bot, "_adapter", None)
                    session = getattr(adapter, "_session", None)
                if session is not None and hasattr(session, "set_pending_tool_policy"):
                    tool_policy = gateway._resolve_tool_policy_for_message(
                        channel_name, facts=facts
                    )
                    session.set_pending_tool_policy(agent, tool_policy)

        logger.info(f"Injected routing handler for channel '{channel_name}'")

    async def _start_telegram_bot_polling(self, name: str, bot: Any) -> None:
        """Start a TelegramBot using low-level PTB API for shared event loop.

        Uses ``initialize() -> start() -> updater.start_polling()`` instead
        of the high-level ``run_polling()`` which owns the event loop.
        """
        try:
            from telegram import Update
            from telegram.ext import (
                Application,
                CommandHandler,
                MessageHandler,
                filters,
            )
        except ImportError:
            logger.error("python-telegram-bot not installed, cannot start Telegram channel")
            return

        app = Application.builder().token(bot._token).build()

        # Copy handlers from the bot's application if it was already built
        # Otherwise, re-build handlers here using the bot's setup logic
        bot._application = app
        bot._started_at = time.time()

        # Get bot info
        bot_info = await app.bot.get_me()
        from praisonaiagents.bots import BotUser
        bot._bot_user = BotUser(
            user_id=str(bot_info.id),
            username=bot_info.username,
            display_name=bot_info.first_name,
            is_bot=True,
        )

        # Set up message handler with routing support
        channel_name = name
        gateway = self

        async def handle_message(update: Update, context: Any):
            # Import the shared security pipeline from telegram.py
            from praisonai_bot.bots.telegram import process_inbound_telegram_message
            
            # Use shared security pipeline for consistent enforcement
            message = await process_inbound_telegram_message(update, bot)
            if not message:
                return  # Message was dropped by security checks

            user_id = message.sender.user_id if message.sender else "unknown"
            message_text = message.content

            # Determine routing context
            chat_type = update.message.chat.type if update.message.chat else "private"
            routing_ctx = gateway._determine_routing_context(
                "telegram", {"chat_type": chat_type}
            )
            # Build richer facts for binding-based routing (Issue #2225)
            chat_id = (
                str(update.message.chat.id)
                if update.message.chat is not None
                else None
            )
            account = bot.bot_user.user_id if getattr(bot, "bot_user", None) else None
            facts = gateway._build_route_facts(
                routing_ctx,
                peer=user_id,
                channel_id=chat_id,
                account=account,
            )
            agent = gateway._resolve_agent_for_message(
                channel_name, routing_ctx, facts=facts
            )
            if not agent:
                agent = bot._agent  # fallback to default
            # Per-route toolset scope for this inbound message (Issue #2298).
            tool_policy = gateway._resolve_tool_policy_for_message(
                channel_name, facts=facts
            )

            # Ack reaction — show processing indicator
            ack_ctx = None
            if bot._ack.enabled:
                async def _tg_react(emoji, **kw):
                    try:
                        from telegram import ReactionTypeEmoji
                        await app.bot.set_message_reaction(
                            chat_id=update.message.chat_id,
                            message_id=update.message.message_id,
                            reaction=[ReactionTypeEmoji(emoji=emoji)],
                        )
                    except Exception:
                        pass
                async def _tg_unreact(emoji, **kw):
                    try:
                        await app.bot.set_message_reaction(
                            chat_id=update.message.chat_id,
                            message_id=update.message.message_id,
                            reaction=[],
                        )
                    except Exception:
                        pass
                ack_ctx = await bot._ack.ack(react_fn=_tg_react)

            try:
                message_text = await bot._debouncer.debounce(user_id, message_text)
                
                # Show typing indicator with renewal during long operation
                if bot.config.typing_indicator:
                    from praisonai_bot.bots._typing_indicator import with_typing_renewal
                    
                    async def _typing_action():
                        await update.message.chat.send_action("typing")
                    
                    response = await with_typing_renewal(
                        typing_func=_typing_action,
                        operation_coro=bot._session.chat(
                            agent, user_id, message_text, tool_policy=tool_policy
                        )
                    )
                else:
                    response = await bot._session.chat(
                        agent, user_id, message_text, tool_policy=tool_policy
                    )
                if hasattr(bot, '_send_response_with_media'):
                    await bot._send_response_with_media(
                        update.message.chat_id,
                        response,
                        reply_to=update.message.message_id,
                    )
                else:
                    await update.message.reply_text(str(response))
                # Done reaction
                if ack_ctx:
                    await bot._ack.done(ack_ctx, react_fn=_tg_react, unreact_fn=_tg_unreact)
            except Exception as e:
                logger.error(f"Agent error in {name}: {safe_log_message(e)}")
                user_error = extract_root_cause_from_error(str(e))
                await update.message.reply_text(f"Error: {safe_error_message(user_error)}")

        async def handle_voice(update: Update, context: Any):
            await handle_message(update, context)

        async def handle_status(update: Update, context: Any):
            if not update.message:
                return
            from praisonai_bot.bots.telegram import process_inbound_telegram_message
            if not await process_inbound_telegram_message(update, bot):
                return
            await update.message.reply_text(bot._format_status())

        async def handle_new(update: Update, context: Any):
            if not update.message:
                return
            from praisonai_bot.bots.telegram import process_inbound_telegram_message
            message = await process_inbound_telegram_message(update, bot)
            if not message:
                return
            user_id = message.sender.user_id if message.sender else "unknown"
            bot._session.reset(user_id)
            await update.message.reply_text("Session reset. Starting fresh conversation.")

        async def handle_help(update: Update, context: Any):
            if not update.message:
                return
            from praisonai_bot.bots.telegram import process_inbound_telegram_message
            if not await process_inbound_telegram_message(update, bot):
                return
            await update.message.reply_text(bot._format_help())

        # Register handlers
        app.add_handler(CommandHandler("status", handle_status))
        app.add_handler(CommandHandler("new", handle_new))
        app.add_handler(CommandHandler("help", handle_help))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

        # Initialize and start using low-level API
        await app.initialize()
        await app.start()
        await app.updater.start_polling(poll_interval=bot.config.polling_interval)

        bot._is_running = True
        logger.info(f"Telegram bot started: @{bot._bot_user.username}")

        # Keep alive until cancelled
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info(f"Stopping Telegram bot '{name}'...")
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            bot._is_running = False

    async def stop_channels(self, drain_timeout: Optional[float] = None) -> None:
        """Gracefully stop all running channel bots.

        Args:
            drain_timeout: Optional graceful-drain window (#2375). When set
                and > 0, channel bots that support a ``drain`` coroutine
                (e.g. ``BotOS``) are first asked to quiesce ingress and let
                in-flight agent turns finish before their tasks are
                cancelled. ``0``/``None`` preserves the prior
                immediate-cancel behaviour.
        """
        # Issue #2375: opt-in graceful drain of in-flight agent turns before
        # we cancel channel tasks. Best-effort and bounded; failures here
        # never block teardown.
        if drain_timeout and drain_timeout > 0:
            # Bound the *total* drain to drain_timeout: track elapsed and
            # pass only the remaining budget to each bot so N channel bots
            # don't multiply the configured window (N * drain_timeout).
            drain_start = time.monotonic()
            for name, bot in list(self._channel_bots.items()):
                drain = getattr(bot, "drain", None)
                if callable(drain):
                    remaining = drain_timeout - (time.monotonic() - drain_start)
                    if remaining <= 0:
                        break
                    try:
                        abandoned = await drain(remaining)
                        if abandoned:
                            logger.warning(
                                "Drain timeout for bot '%s': %d turn(s) abandoned",
                                name, abandoned,
                            )
                    except Exception as e:
                        logger.warning("Error draining bot '%s': %s", name, e)

        # Stop health monitoring first
        await self._channel_supervisor.stop_health_monitoring()
        
        for task in self._channel_tasks.values():
            task.cancel()

        if self._channel_tasks:
            await asyncio.gather(*self._channel_tasks.values(), return_exceptions=True)
            self._channel_tasks.clear()

        for name, bot in list(self._channel_bots.items()):
            try:
                if hasattr(bot, "stop"):
                    await bot.stop()
                logger.info(f"Stopped bot '{name}'")
            except Exception as e:
                logger.error(f"Error stopping bot '{name}': {e}")

        # Clean up supervisor state for all channels
        for name in list(self._channel_bots.keys()):
            self._channel_supervisor.cleanup(name)

        self._channel_bots.clear()
        self._routing_rules.clear()
        self._routing_bindings.clear()

    def _diff_config_paths(self, old: Dict[str, Any], new: Dict[str, Any], prefix: str = "") -> Set[str]:
        """Find all paths that differ between old and new configs.
        
        Args:
            old: Old configuration dictionary
            new: New configuration dictionary
            prefix: Current path prefix for recursion
            
        Returns:
            Set of dotted paths where configs differ
        """
        changed = set()
        
        # Check for added/removed keys
        old_keys = set(old.keys()) if old else set()
        new_keys = set(new.keys()) if new else set()
        
        # Keys removed
        for key in old_keys - new_keys:
            path = f"{prefix}.{key}" if prefix else key
            changed.add(path)
        
        # Keys added
        for key in new_keys - old_keys:
            path = f"{prefix}.{key}" if prefix else key
            changed.add(path)
        
        # Keys present in both - check for changes
        for key in old_keys & new_keys:
            path = f"{prefix}.{key}" if prefix else key
            old_val = old[key]
            new_val = new[key]
            
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                # Recurse into nested dicts
                sub_changes = self._diff_config_paths(old_val, new_val, path)
                changed.update(sub_changes)
            elif old_val != new_val:
                changed.add(path)
        
        return changed
    
    def _build_reload_plan(self, changed_paths: Set[str]) -> ReloadPlan:
        """Build a selective reload plan based on changed config paths.
        
        Args:
            changed_paths: Set of dotted paths that changed
            
        Returns:
            ReloadPlan with actions to take
        """
        plan = ReloadPlan()
        
        for path in changed_paths:
            parts = path.split(".")
            
            if not parts:
                continue
            
            # Top-level section changes
            if parts[0] == "agents":
                if len(parts) == 1:
                    # Entire agents section changed
                    plan.reload_agents = True
                elif len(parts) >= 2:
                    # Specific agent or agent property changed
                    plan.reload_agents = True
                    
            elif parts[0] == "channels":
                if len(parts) == 1:
                    # Entire channels section changed - need full restart
                    plan.requires_full_restart()
                elif len(parts) >= 2:
                    # Specific channel changed
                    channel_name = parts[1]
                    plan.add_channel_restart(channel_name)
                    
            elif parts[0] == "provider":
                # Provider changes affect agents if they use default model
                plan.reload_agents = True
                
            elif parts[0] == "guardrails":
                # Guardrails changes affect agents
                plan.reload_agents = True
                
            elif parts[0] in ["scheduler", "routes", "routing"]:
                # These are structural changes requiring full restart
                plan.requires_full_restart()
                
            else:
                # Unknown section - be safe and do full restart
                logger.warning(f"Unknown config section changed: {parts[0]} - triggering full restart")
                plan.requires_full_restart()
        
        return plan
    
    async def _restart_channel(
        self,
        channel_name: str,
        channels_cfg: Dict[str, Any],
        drain_timeout: Optional[float] = None,
    ) -> None:
        """Restart a single channel with new configuration.
        
        Args:
            channel_name: Name of the channel to restart
            channels_cfg: Full channels configuration
            drain_timeout: Issue #2533 — optional bounded drain window. When
                set and > 0, the channel's bot is first asked to quiesce
                ingress and let in-flight agent turns finish (reusing the
                bot's ``drain`` coroutine) before its task is cancelled.
                ``None``/0 preserves the prior immediate-restart behaviour.
        """
        logger.info(f"Restarting channel '{channel_name}'...")

        # Issue #2533: drain in-flight turns on this channel before tearing it
        # down, so a reload-driven restart doesn't cut active work. Best-effort
        # and bounded; failures here never block the restart.
        if drain_timeout and drain_timeout > 0:
            bot = self._channel_bots.get(channel_name)
            drain = getattr(bot, "drain", None) if bot is not None else None
            if callable(drain):
                try:
                    abandoned = await drain(drain_timeout)
                    if abandoned:
                        logger.warning(
                            "Drain timeout for channel '%s' during reload: "
                            "%d turn(s) abandoned",
                            channel_name, abandoned,
                        )
                except Exception as e:
                    logger.warning(
                        "Error draining channel '%s' during reload: %s",
                        channel_name, e,
                    )

        # Cancel the existing task first
        if channel_name in self._channel_tasks:
            task = self._channel_tasks[channel_name]
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            del self._channel_tasks[channel_name]
        
        # Stop and clean up the existing bot
        if channel_name in self._channel_bots:
            # Stop the bot
            bot = self._channel_bots[channel_name]
            try:
                if hasattr(bot, "stop"):
                    await bot.stop()
            except Exception as e:
                logger.error(f"Error stopping bot '{channel_name}': {e}")
            
            # Remove from tracking
            del self._channel_bots[channel_name]
            
            # Clean up supervisor state
            self._channel_supervisor.cleanup(channel_name)
        
        # Remove old routing rules
        if channel_name in self._routing_rules:
            del self._routing_rules[channel_name]
        if channel_name in self._routing_bindings:
            del self._routing_bindings[channel_name]
        
        # Start the channel again with new config
        if channel_name in channels_cfg:
            ch_cfg = channels_cfg[channel_name]
            await self._start_single_channel(channel_name, ch_cfg)
    
    async def _start_single_channel(self, channel_name: str, ch_cfg: Dict[str, Any]) -> None:
        """Start a single channel with given configuration.
        
        Args:
            channel_name: Name of the channel
            ch_cfg: Channel configuration
        """
        from praisonaiagents.bots import BotConfig
        
        channel_type = ch_cfg.get("platform", channel_name).lower()
        token = ch_cfg.get("token", "")
        
        # WhatsApp web mode doesn't require a token
        wa_web_mode = (channel_type == "whatsapp" and
                       ch_cfg.get("mode", "cloud").lower().strip() == "web")
        # Email/AgentMail use env vars for tokens — not required in YAML
        is_email_platform = channel_type in ("email", "agentmail")
        
        if not token and not wa_web_mode and not is_email_platform:
            logger.warning(f"No token for channel '{channel_name}', skipping")
            return
        
        routes = ch_cfg.get("routing") or ch_cfg.get("routes") or {"default": "default"}
        self._routing_rules[channel_name] = routes
        self._routing_bindings[channel_name] = self._parse_bindings(
            ch_cfg.get("bindings")
        )
        
        # Resolve default agent for this channel
        default_agent_id = routes.get("default", next(iter(self._agents.keys())) if self._agents else "default")
        default_agent = self._agents.get(default_agent_id)
        if not default_agent:
            logger.warning(f"Default agent '{default_agent_id}' not found for channel '{channel_name}', skipping")
            return
        
        # Extract configuration (same as in start_channels)
        _raw_allowed = ch_cfg.get("allowed_users") or []
        if isinstance(_raw_allowed, str):
            _raw_allowed = [s.strip() for s in _raw_allowed.split(",") if s.strip()]
        
        _raw_channels = ch_cfg.get("allowed_channels") or []
        if isinstance(_raw_channels, str):
            _raw_channels = [s.strip() for s in _raw_channels.split(",") if s.strip()]
        
        group_policy = ch_cfg.get("group_policy", "mention_only")
        mention_required = (group_policy == "mention_only")
        
        # Extract auto_approve_tools setting (align with start_channels parsing)
        _raw_auto_approve = ch_cfg.get("auto_approve_tools")
        if _raw_auto_approve is None:
            auto_approve_tools = True
        elif isinstance(_raw_auto_approve, str):
            auto_approve_tools = _raw_auto_approve.strip().lower() in ("1", "true", "yes", "on")
        else:
            auto_approve_tools = bool(_raw_auto_approve)
        
        config_kwargs = dict(
            token=token,
            allowed_users=list(_raw_allowed),
            allowed_channels=list(_raw_channels),
            mention_required=mention_required,
            group_policy=group_policy,
            auto_approve_tools=auto_approve_tools,
        )

        # Issue #2855: wire the inbound admission policy on hot-reload too, so a
        # reloaded channel honours the same YAML knobs as start_channels().
        _raw_uup = ch_cfg.get("unknown_user_policy")
        if isinstance(_raw_uup, str) and _raw_uup.strip():
            config_kwargs["unknown_user_policy"] = _raw_uup.strip().lower()
        _raw_owner = ch_cfg.get("owner_user_id")
        if _raw_owner is not None and str(_raw_owner).strip():
            config_kwargs["owner_user_id"] = str(_raw_owner).strip()

        # Only pass default_tools when the channel explicitly overrides it
        _raw_yaml_tools = ch_cfg.get("default_tools")
        if isinstance(_raw_yaml_tools, list):
            config_kwargs["default_tools"] = _raw_yaml_tools
        
        config = BotConfig(**config_kwargs)

        # Issue #2721: carry the inbound STT policy through metadata (same as
        # start_channels) so a hot-reloaded channel still transcribes voice.
        _raw_stt = ch_cfg.get("stt")
        if _raw_stt is not None:
            try:
                config.metadata["stt"] = _raw_stt
            except Exception:  # pragma: no cover — defensive
                pass

        # Warn if no allowlist is configured (Issue #2855: deny-aware message).
        if not config.allowed_users:
            self._warn_empty_allowlist(channel_name, config.unknown_user_policy)
        
        # Create the bot using the same pattern as start_channels
        try:
            bot = self._create_bot(channel_type, token, default_agent, config, ch_cfg)
            if bot is None:
                return
            # Issue #2721: enable inbound STT on the hot-reloaded channel too.
            self._enable_stt(bot, config)
            # Issue #2454: stamp the shared admission gate so a channel restarted
            # during hot-reload still enforces the global concurrency ceiling.
            self._stamp_admission_gate(bot)
            # Issue #3020: stamp the identity resolver on the hot-reloaded
            # channel too, so a restarted channel keeps cross-platform continuity.
            self._stamp_identity_resolver(bot)
            self._channel_bots[channel_name] = bot
            logger.info(f"Channel '{channel_name}' ({channel_type}) initialized")
        except Exception as e:
            logger.error(f"Failed to create bot for '{channel_name}': {e}")
            return
        
        # Start the bot using the same pattern as start_channels
        task = asyncio.create_task(self._run_bot_safe(channel_name, bot))
        self._channel_tasks[channel_name] = task
        logger.info(f"Started channel '{channel_name}' ({channel_type})")

    async def reload_config(self, config_path: str) -> None:
        """Hot-reload gateway.yaml with diff-driven selective restart.

        Only restarts affected subsystems based on what changed:
        - Agent changes: recreate agents only
        - Single channel changes: restart that channel only
        - Structural changes: full restart (fallback)

        The WebSocket server itself is never restarted.

        Issue #2533: serialized behind ``_reload_lock`` so overlapping triggers
        (file watcher, SIGHUP, back-to-back SIGHUPs) apply one at a time and
        cannot interleave channel/agent mutations across await points.
        """
        # Bind the lock to the running loop lazily; ``__init__`` may run before
        # a loop exists.
        if self._reload_lock is None:
            self._reload_lock = asyncio.Lock()
        async with self._reload_lock:
            await self._reload_config_locked(config_path)

    def _record_reload_status(
        self,
        last_result: str,
        *,
        changed_paths: Tuple[str, ...] = (),
        error: Optional[str] = None,
    ) -> None:
        """Record the outcome of a reload attempt for ``health()`` (Issue #3049).

        Preserves the watcher-liveness flag so a bad edit is visibly *rejected*
        rather than silently ineffective, and operators can see it without
        scraping logs.
        """
        self._reload_status = ReloadStatus(
            watcher="active" if self._reload_watcher_active else "disabled",
            last_result=last_result,
            last_at=time.time(),
            changed_paths=changed_paths,
            error=error,
        )

    async def _reload_config_locked(self, config_path: str) -> None:
        """Perform the actual hot-reload. Callers must hold ``_reload_lock``."""
        logger.info(f"Hot-reloading gateway config from {config_path}...")
        self._config_path = config_path
        try:
            new_cfg = self.load_gateway_config(config_path)
        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Reload failed — config invalid: {e}")
            # Issue #3049: record the failure so the operator sees the edit was
            # rejected in health() instead of just a log line.
            self._record_reload_status("failed", error=str(e))
            return

        # Issue #3020: reconcile the cross-platform identity resolver from the
        # (possibly changed) top-level ``identity:`` block *before* any channel
        # is (re)started below, so freshly created bots are stamped with the
        # new resolver instead of a stale one. An explicit constructor/CLI
        # resolver is preserved; an unchanged block keeps its live link cache.
        self._reconcile_identity_resolver(new_cfg.get("identity"))

        # First time loading - do full setup
        if self._loaded_config is None:
            # Issue #3049: don't publish the applied revision until the runtime
            # (channels + agents) has actually been brought up. If any awaited
            # step below raises, we record a ``failed`` outcome and leave the
            # applied revision unset instead of falsely reporting the new config
            # as live.
            try:
                await self.stop_channels()

                # Create agents
                agents_cfg = new_cfg.get("agents", {})
                provider_cfg = new_cfg.get("provider", {})
                default_model = provider_cfg.get("model") if provider_cfg else None
                guardrails_cfg = (new_cfg.get("guardrails") or {}).get("registry")
                if agents_cfg:
                    self._agents.clear()
                    self._create_agents_from_config(
                        agents_cfg,
                        default_model=default_model,
                        guardrails_cfg=guardrails_cfg,
                    )

                # Register inbound trigger hooks (Issue #2281).
                self._apply_hooks_from_config(new_cfg)

                # Start channels
                channels_cfg = new_cfg.get("channels", {})
                if channels_cfg:
                    await self.start_channels(channels_cfg)
            except Exception as e:
                logger.error(f"Initial config load failed during setup: {e}")
                self._record_reload_status("failed", error=str(e))
                raise

            # Setup succeeded — now the runtime genuinely reflects this config.
            self._loaded_config = new_cfg
            self._applied_config_revision = compute_config_revision(new_cfg)
            logger.info("Initial config load complete")
            self._record_reload_status("ok")
            return
        
        # Diff the configs to find what changed
        changed_paths = self._diff_config_paths(self._loaded_config, new_cfg)
        
        if not changed_paths:
            logger.info("No changes detected in config")
            self._record_reload_status("no_changes")
            return
        
        logger.info(f"Config changes detected: {changed_paths}")
        
        # Build reload plan
        plan = self._build_reload_plan(changed_paths)
        
        # Execute reload plan
        if plan.full_restart:
            logger.info("Performing full restart due to structural changes")
            # Issue #2533: drain in-flight turns before bouncing all channels.
            await self.stop_channels(drain_timeout=self._reload_drain_timeout)
            
            # Recreate agents
            agents_cfg = new_cfg.get("agents", {})
            provider_cfg = new_cfg.get("provider", {})
            default_model = provider_cfg.get("model") if provider_cfg else None
            guardrails_cfg = (new_cfg.get("guardrails") or {}).get("registry")
            if agents_cfg:
                self._agents.clear()
                self._create_agents_from_config(
                    agents_cfg,
                    default_model=default_model,
                    guardrails_cfg=guardrails_cfg,
                )
            
            # Restart all channels
            channels_cfg = new_cfg.get("channels", {})
            if channels_cfg:
                await self.start_channels(channels_cfg)
        else:
            # Selective reload
            if plan.reload_agents:
                logger.info("Reloading agents...")
                agents_cfg = new_cfg.get("agents", {})
                provider_cfg = new_cfg.get("provider", {})
                default_model = provider_cfg.get("model") if provider_cfg else None
                guardrails_cfg = (new_cfg.get("guardrails") or {}).get("registry")
                if agents_cfg:
                    self._agents.clear()
                    self._create_agents_from_config(
                        agents_cfg,
                        default_model=default_model,
                        guardrails_cfg=guardrails_cfg,
                    )
                logger.info("Agents reloaded")
            
            # Restart specific channels
            channels_cfg = new_cfg.get("channels", {})
            for channel_name in plan.restart_channels:
                # Issue #2533: drain in-flight turns on this channel first.
                await self._restart_channel(
                    channel_name,
                    channels_cfg,
                    drain_timeout=self._reload_drain_timeout,
                )
            
            # Apply hot-reload paths (future enhancement)
            if plan.hot_reload_paths:
                logger.info(f"Hot-reload paths (no-op for now): {plan.hot_reload_paths}")

        # Surface a concise summary of what the reload did (Issue #2533).
        if plan.full_restart:
            logger.info("reload applied: full restart")
        else:
            summary_parts = []
            if plan.reload_agents:
                summary_parts.append("agents")
            if plan.restart_channels:
                summary_parts.append(
                    "restart[" + ",".join(sorted(plan.restart_channels)) + "]"
                )
            if plan.hot_reload_paths:
                summary_parts.append(
                    "hot[" + ",".join(sorted(plan.hot_reload_paths)) + "]"
                )
            if summary_parts:
                logger.info("reload applied: " + "; ".join(summary_parts))
        
        # Refresh inbound trigger hooks (Issue #2281) so removed hooks and
        # rotated hook secrets take effect without a full process restart.
        self._apply_hooks_from_config(new_cfg)

        # Issue #2661: pick up a rotated shared gateway secret and force-close
        # every live session that authenticated under the previous secret, so a
        # leaked/revoked credential stops working within one reload cycle
        # without a full process restart.
        await self._apply_auth_secret_rotation(new_cfg)

        # Update stored config
        self._loaded_config = new_cfg
        # Issue #3049: the config the gateway is *actually running* now has a
        # new revision; record it so health() can be compared against the
        # on-disk revision for drift detection, and record the successful
        # reload outcome with the paths that changed.
        self._applied_config_revision = compute_config_revision(new_cfg)
        self._record_reload_status(
            "ok", changed_paths=tuple(sorted(changed_paths))
        )
        logger.info("Hot-reload complete")

    async def _apply_auth_secret_rotation(self, new_cfg: Dict[str, Any]) -> int:
        """Adopt a rotated shared secret and revoke stale live sessions.

        Issue #2661: the reload loop refreshes hook secrets but historically
        left the *gateway* shared secret and every already-authenticated
        WebSocket session untouched. This reads the new ``gateway.auth_token``
        (with env substitution, matching :meth:`load_gateway_config`), and when
        it differs from the running secret updates ``self.config.auth_token``,
        keeps ``GATEWAY_AUTH_TOKEN`` in sync, and force-closes every session
        stamped with the old secret via :meth:`_revoke_rotated_sessions`.

        The behaviour defaults on; set ``gateway.revoke_on_secret_rotation:
        false`` in the config to opt out (the secret is still adopted for new
        connections, but live sessions are left connected).

        Returns:
            The number of sessions revoked (0 when nothing changed or the
            feature is disabled).
        """
        gateway_cfg = new_cfg.get("gateway", {}) if isinstance(new_cfg, dict) else {}
        if not isinstance(gateway_cfg, dict):
            return 0
        if "auth_token" not in gateway_cfg:
            # No secret declared in the new config: leave the running secret
            # (and every live session) untouched.
            return 0

        raw_token = gateway_cfg.get("auth_token")
        # YAML without quotes (e.g. ``auth_token: 12345``) parses as int/other;
        # coerce to str so env substitution and ``os.environ`` assignment below
        # never raise ``TypeError`` and leave the reload partially applied.
        if isinstance(raw_token, str):
            new_token = self._substitute_env_vars(raw_token)
        elif raw_token is None:
            new_token = raw_token
        else:
            new_token = str(raw_token)
        current_token = getattr(self.config, "auth_token", None)
        if not new_token:
            # ``auth_token`` was declared but resolves to empty (e.g. unquoted
            # empty string, or an unset ``${VAR}``). Surface it so an operator
            # clearing the secret isn't left guessing why nothing changed.
            if current_token:
                logger.warning(
                    "Gateway auth_token present in reloaded config but resolved "
                    "to empty; keeping the previous secret and live sessions"
                )
            return 0
        if new_token == current_token:
            return 0

        # Adopt the new secret so subsequent handshakes authenticate against it.
        self.config.auth_token = new_token
        os.environ["GATEWAY_AUTH_TOKEN"] = new_token
        logger.info("Gateway auth secret rotated via config reload")

        # Normalise the toggle: env-substituted YAML arrives as a string, so a
        # raw truthiness check would treat "false"/"0" as enabled. Default on.
        revoke_raw = gateway_cfg.get("revoke_on_secret_rotation", True)
        if isinstance(revoke_raw, str):
            revoke_enabled = revoke_raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            revoke_enabled = bool(revoke_raw)
        if not revoke_enabled:
            logger.info(
                "revoke_on_secret_rotation disabled; leaving live sessions "
                "connected under the previous secret"
            )
            return 0
        return await self._revoke_rotated_sessions()

    async def _watch_config(self, config_path: str, poll_interval: float = 5.0, debounce: float = 1.0) -> None:
        """Watch the config file for changes and trigger hot-reload.

        Issue #2533: prefer event-driven watching via ``watchdog`` (inotify /
        FSEvents / ReadDirectoryChangesW) so config changes apply promptly.
        ``watchdog`` is an optional, lazily-imported dependency; when it is
        unavailable — or inotify watches are exhausted — this degrades
        gracefully to the previous mtime-polling loop.

        Args:
            config_path: Path to the config file
            poll_interval: How often to check for changes when polling (seconds)
            debounce: Wait time after detecting change before reloading (seconds)
        """
        self._config_path = config_path
        # Issue #3049: mark hot-reload liveness "active" for the health surface
        # while a watcher (event-driven or polling) is running, and flip it to
        # "disabled" only when the watcher genuinely gives up — so silent
        # degradation is observable rather than assumed-working.
        self._reload_watcher_active = True
        try:
            if await self._watch_config_event_driven(config_path, debounce=debounce):
                return
            logger.info(
                "Config watcher: event-driven watching unavailable, "
                "falling back to %.1fs polling", poll_interval,
            )
            await self._watch_config_polling(
                config_path, poll_interval=poll_interval, debounce=debounce
            )
        except asyncio.CancelledError:
            raise
        finally:
            # The watcher has stopped (fell through, errored, or was cancelled);
            # hot-reload is no longer active.
            self._reload_watcher_active = False

    async def _config_settled(self, config_path: str, debounce: float = 1.0) -> bool:
        """Return ``True`` once the config file's mtime has stopped changing.

        Issue #2533: the event-driven watcher can wake mid-write. We sample the
        mtime, wait a short quiet window, then re-sample; a stable mtime means
        the write has completed and the file is safe to parse. A missing file
        (mid ``rename``/truncate) counts as not-yet-settled so the caller re-arms
        rather than treating it as a hard failure.
        """
        try:
            first = os.path.getmtime(config_path)
        except OSError:
            return False
        await asyncio.sleep(min(debounce, 0.5))
        try:
            second = os.path.getmtime(config_path)
        except OSError:
            return False
        return first == second

    async def _watch_config_event_driven(self, config_path: str, debounce: float = 1.0) -> bool:
        """Event-driven config watch using the optional ``watchdog`` package.

        Returns ``True`` when it ran an event-driven watch loop (until the task
        is cancelled), or ``False`` immediately when ``watchdog`` is not
        installed / could not start an observer, so the caller can fall back to
        polling.
        """
        try:
            from watchdog.observers import Observer  # type: ignore
            from watchdog.events import FileSystemEventHandler  # type: ignore
        except Exception:
            return False

        loop = asyncio.get_event_loop()
        change_event = asyncio.Event()
        watch_path = os.path.abspath(config_path)
        watch_dir = os.path.dirname(watch_path) or "."

        class _ConfigChangeHandler(FileSystemEventHandler):  # pragma: no cover - thin adapter
            def _notify(self, event):
                try:
                    src = getattr(event, "src_path", "") or ""
                    dest = getattr(event, "dest_path", "") or ""
                    if os.path.abspath(src) == watch_path or (
                        dest and os.path.abspath(dest) == watch_path
                    ):
                        loop.call_soon_threadsafe(change_event.set)
                except Exception:
                    pass

            def on_modified(self, event):
                self._notify(event)

            def on_created(self, event):
                self._notify(event)

            def on_moved(self, event):
                self._notify(event)

        observer = Observer()
        try:
            observer.schedule(_ConfigChangeHandler(), watch_dir, recursive=False)
            observer.start()
        except Exception as e:
            logger.debug("Could not start watchdog observer: %s", e)
            try:
                observer.stop()
            except Exception:
                pass
            return False

        logger.info(
            "Config watcher active (event-driven) for %s", config_path
        )
        try:
            while True:
                await change_event.wait()
                change_event.clear()
                # Debounce rapid consecutive writes: coalesce a burst of events
                # by waiting for a quiet window before reloading.
                await asyncio.sleep(debounce)
                change_event.clear()
                # Issue #2533: guard against partial/slow writes. A single slow
                # write can still be in progress after the debounce window, so
                # verify the file's mtime has settled before parsing. If it is
                # still changing, skip this cycle and re-arm the event so the
                # completed write is applied on the next quiet window rather
                # than dropped after a parse failure.
                if not await self._config_settled(config_path, debounce):
                    change_event.set()
                    continue
                try:
                    self.load_gateway_config(config_path)
                    await self.reload_config(config_path)
                except Exception as e:
                    logger.error(
                        "Config reload failed, keeping last-known-good: %s", e
                    )
        except asyncio.CancelledError:
            raise
        finally:
            try:
                observer.stop()
                observer.join(timeout=2.0)
            except Exception:
                pass
        return True

    async def _watch_config_polling(self, config_path: str, poll_interval: float = 5.0, debounce: float = 1.0) -> None:
        """Poll the config file for changes and trigger hot-reload.
        
        Args:
            config_path: Path to the config file
            poll_interval: How often to check for changes (seconds)
            debounce: Wait time after detecting change before reloading (seconds)
        """
        last_mtime: float = 0.0
        last_known_good_config = None
        pending_reload = False
        
        try:
            last_mtime = os.path.getmtime(config_path)
            # Store initial config as last-known-good
            last_known_good_config = self.load_gateway_config(config_path)
        except OSError as e:
            logger.warning(f"Could not read initial config mtime: {e}")
        except Exception as e:
            logger.error(f"Could not load initial config: {e}")

        while True:
            await asyncio.sleep(poll_interval)
            try:
                mtime = os.path.getmtime(config_path)
                if mtime > last_mtime:
                    if not pending_reload:
                        logger.info(f"Config change detected, waiting {debounce}s for changes to settle...")
                        pending_reload = True
                    last_mtime = mtime
                    
                    # Wait for debounce period to handle rapid consecutive writes
                    await asyncio.sleep(debounce)
                    
                    # Check if file was modified again during debounce
                    current_mtime = os.path.getmtime(config_path)
                    if current_mtime > last_mtime:
                        # File still being written, skip this cycle
                        continue
                    
                    pending_reload = False
                    
                    # Validate config before applying
                    try:
                        test_cfg = self.load_gateway_config(config_path)
                        last_known_good_config = test_cfg
                        await self.reload_config(config_path)
                    except Exception as e:
                        logger.error(f"Config reload failed, keeping last-known-good: {e}")
                        # Could restore last_known_good_config here if needed
                        
            except asyncio.CancelledError:
                break
            except OSError as e:
                # File might be temporarily unavailable during write
                logger.debug(f"Config file temporarily unavailable: {e}")
            except Exception as e:
                logger.warning(f"Config watch error: {e}")

    # Channel supervision control methods
    
    def pause_channel(self, name: str) -> bool:
        """Pause a channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel was paused, False if not found or not running
        """
        return self._channel_supervisor.pause(name)
    
    def resume_channel(self, name: str) -> bool:
        """Resume a paused channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel was resumed, False if not found or not paused
        """
        return self._channel_supervisor.resume(name)
    
    def reconnect_channel(self, name: str) -> bool:
        """Force reconnect a channel.
        
        Args:
            name: Channel name
            
        Returns:
            True if channel exists, False otherwise
        """
        return self._channel_supervisor.reconnect(name)
    
    def get_channel_supervision_status(self) -> Dict[str, Any]:
        """Get supervision status for all channels.
        
        Returns:
            Dictionary mapping channel names to their supervision status
        """
        status_dict = {}
        for name, status in self._channel_supervisor.get_all_status().items():
            status_dict[name] = {
                "state": status.state.value,
                "last_error": status.last_error,
                "last_error_time": status.last_error_time,
                "next_retry_at": status.next_retry_at,
                "total_recoveries": status.total_recoveries,
                "manual_pause": status.manual_pause,
            }
        return status_dict
    
    def get_health_monitor_status(self) -> Dict[str, Any]:
        """Get health monitor status.
        
        Returns:
            Dictionary with health monitor status and channel health information
        """
        return self._channel_supervisor.get_health_status()

    async def start_with_config(self, config_path: str) -> None:
        """Start the gateway with a gateway.yaml configuration.

        This loads agents from the config, starts channel bots, then
        starts the WebSocket server.  All run concurrently.

        Args:
            config_path: Path to gateway.yaml.
        """
        cfg = self.load_gateway_config(config_path)
        
        # Store initial config for diff-driven reload
        self._loaded_config = cfg
        # Issue #3049: record the config source + the applied revision at
        # startup so health() can report which revision is running and detect
        # drift against the on-disk file even before any hot-reload occurs.
        self._config_path = config_path
        self._applied_config_revision = compute_config_revision(cfg)

        # Issue #3020: build the cross-platform identity resolver from the
        # declarative top-level ``identity:`` block so a paired/linked user
        # keeps one continuous session + memory across channels. A resolver
        # passed to the constructor always wins over the YAML block.
        self._reconcile_identity_resolver(cfg.get("identity"))

        # Apply gateway section overrides
        gw_cfg = cfg.get("gateway", {})
        if gw_cfg.get("host"):
            self._host = gw_cfg["host"]
        if gw_cfg.get("port"):
            self._port = int(gw_cfg["port"])
        # Propagate slow-consumer flow-control limits so YAML/CLI users get the
        # configured ceilings instead of the in-memory defaults when clients
        # register via ``_register_client_conn``.
        if "max_buffered_bytes" in gw_cfg:
            self.config.max_buffered_bytes = int(gw_cfg["max_buffered_bytes"])
        if "max_queued_frames" in gw_cfg:
            self.config.max_queued_frames = int(gw_cfg["max_queued_frames"])
        # Issue #2715: additive OpenAI-compatible / MCP protocol surfaces.
        # YAML ``gateway.api: { openai: true, mcp: true }`` enables them; a
        # CLI ``--openai-api`` / ``--mcp`` override (stamped on the instance)
        # wins so operators can toggle without editing the file.
        api_yaml = gw_cfg.get("api")
        if isinstance(api_yaml, dict):
            if "openai" in api_yaml:
                self.config.api.openai = bool(api_yaml["openai"])
            if "mcp" in api_yaml:
                self.config.api.mcp = bool(api_yaml["mcp"])
        _openai_ovr = getattr(self, "_openai_api_override", None)
        if _openai_ovr is not None:
            self.config.api.openai = bool(_openai_ovr)
        _mcp_ovr = getattr(self, "_mcp_override", None)
        if _mcp_ovr is not None:
            self.config.api.mcp = bool(_mcp_ovr)
        # Issue #2375: graceful-drain timeout on shutdown. When set, the
        # shutdown path waits (bounded) for in-flight turns/sessions to
        # finish before tearing down. 0/unset preserves prior behaviour.
        # A CLI ``--drain-timeout`` override (set on the instance) wins
        # over the YAML value.
        drain_timeout_cfg = getattr(self, "_drain_timeout_override", None)
        if drain_timeout_cfg is None:
            drain_timeout_cfg = gw_cfg.get("drain_timeout")
        # YAML/env-substituted values may arrive as strings (e.g. "30");
        # coerce once so later ``> 0`` comparisons never raise TypeError.
        if drain_timeout_cfg is not None:
            try:
                import math as _math
                drain_timeout_cfg = float(drain_timeout_cfg)
                if not _math.isfinite(drain_timeout_cfg) or drain_timeout_cfg < 0:
                    raise ValueError
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid gateway.drain_timeout %r; disabling drain",
                    drain_timeout_cfg,
                )
                drain_timeout_cfg = None

        # Issue #2533: bounded drain window for reload-driven channel restarts.
        # A dedicated ``gateway.reload_drain_timeout`` (or CLI override) wins;
        # otherwise fall back to the shutdown ``drain_timeout`` so reloads are
        # drain-coordinated by default when a shutdown drain is configured.
        reload_drain_cfg = getattr(self, "_reload_drain_timeout_override", None)
        if reload_drain_cfg is None:
            reload_drain_cfg = gw_cfg.get("reload_drain_timeout")
        if reload_drain_cfg is None:
            reload_drain_cfg = drain_timeout_cfg
        if reload_drain_cfg is not None:
            try:
                import math as _math
                reload_drain_cfg = float(reload_drain_cfg)
                if not _math.isfinite(reload_drain_cfg) or reload_drain_cfg < 0:
                    raise ValueError
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid gateway.reload_drain_timeout %r; disabling "
                    "reload drain",
                    reload_drain_cfg,
                )
                reload_drain_cfg = None
        self._reload_drain_timeout = reload_drain_cfg

        # Issue #2454: gateway-wide inbound admission control. Build a single
        # shared admission gate from the gateway config (CLI overrides win over
        # YAML) and stamp it onto each channel bot in ``start_channels`` so the
        # concurrency ceiling / fair queue / overflow policy is enforced on the
        # inbound run-dispatch path. Disabled (no gate) when no positive
        # ceiling is configured — preserving today's immediate-dispatch path.
        def _ovr(attr: str, key: str, default: Any) -> Any:
            val = getattr(self, attr, None)
            if val is None:
                val = gw_cfg.get(key, default)
            return val

        # Coerce + validate admission config. Invalid config is fail-fast: a
        # typo in the overload-control knobs must NOT silently start the
        # gateway with unbounded inbound runs (which would remove the very
        # protection the operator asked for). ``build_admission_gate`` raises
        # ``ValueError`` on bad values; we let that propagate to abort startup.
        try:
            _max_runs = int(_ovr("_max_concurrent_runs_override", "max_concurrent_runs", 0) or 0)
            _queue_depth = int(_ovr("_queue_depth_override", "queue_depth", 0) or 0)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"Invalid gateway admission config "
                f"(max_concurrent_runs/queue_depth must be integers): {e}"
            ) from e
        _overflow = str(_ovr("_overflow_policy_override", "overflow_policy", "reject") or "reject")

        # Issue #2531: single reliability posture. A ``reliability`` preset
        # (CLI ``--reliability`` override wins over ``gateway.reliability``)
        # composes the drain window + admission ceiling in one switch, filling
        # only the fields left unset above so explicit ``drain_timeout`` /
        # ``max_concurrent_runs`` / ``overflow_policy`` always override it.
        _reliability = getattr(self, "_reliability_override", None)
        if _reliability is None:
            _reliability = gw_cfg.get("reliability")
        try:
            from ..bots._reliability import resolve_reliability

            _resolved = resolve_reliability(
                _reliability,
                drain_timeout=drain_timeout_cfg,
                max_concurrent_runs=_max_runs,
                queue_depth=_queue_depth,
                overflow_policy=_overflow,
            )
            drain_timeout_cfg = _resolved.drain_timeout
            _max_runs = _resolved.max_concurrent_runs
            _queue_depth = _resolved.queue_depth
            _overflow = _resolved.overflow_policy
        except ValueError as e:
            # A typo in the reliability profile must fail fast rather than
            # silently degrade robustness.
            raise ValueError(f"Invalid gateway reliability config: {e}") from e

        from ..bots._admission import build_admission_gate
        self._admission_gate = build_admission_gate(
            max_concurrent_runs=_max_runs,
            queue_depth=_queue_depth,
            overflow_policy=_overflow,
        )
        if self._admission_gate is not None:
            logger.info(
                "Gateway admission control enabled "
                "(max_concurrent_runs=%d queue_depth=%d overflow=%s)",
                _max_runs, _queue_depth, _overflow,
            )

        # Parse health monitoring configuration
        health_cfg = gw_cfg.get("health")
        if health_cfg and isinstance(health_cfg, dict):
            from .health_monitor import HealthMonitorConfig
            self._health_config = HealthMonitorConfig.from_dict(health_cfg)
            # Recreate supervisor with health config
            self._channel_supervisor = ChannelSupervisor(health_config=self._health_config)

        # Create agents
        agents_cfg = cfg.get("agents", {})
        provider_cfg = cfg.get("provider", {})
        default_model = provider_cfg.get("model") if provider_cfg else None
        guardrails_cfg = (cfg.get("guardrails") or {}).get("registry")
        if agents_cfg:
            self._create_agents_from_config(
                agents_cfg,
                default_model=default_model,
                guardrails_cfg=guardrails_cfg,
            )

        # Register inbound trigger hooks (Issue #2281). Hooks may live at the
        # top level (``hooks:``) or nested under ``gateway:`` for grouping.
        self._apply_hooks_from_config(cfg)

        # Issue #3021: opt-in gateway lifecycle (idle/scale-to-zero, epoch-aware
        # external drain marker, crash-loop guard). Accept the block at the top
        # level (``lifecycle:``) or nested under ``gateway:``. No-op when unset.
        lifecycle_cfg = cfg.get("lifecycle", gw_cfg.get("lifecycle"))
        # CLI overrides (stamped on the instance) win over / synthesise the YAML.
        lifecycle_cfg = self._merge_lifecycle_overrides(lifecycle_cfg, drain_timeout_cfg)
        self._configure_lifecycle(lifecycle_cfg)

        # Start channels + WebSocket server concurrently
        channels_cfg = cfg.get("channels", {})

        # Start config file watcher for hot-reload
        self._config_watch_task = None

        async def _run_all():
            if channels_cfg:
                await self.start_channels(channels_cfg)
            # Launch config watcher in background
            self._config_watch_task = asyncio.create_task(
                self._watch_config(config_path)
            )
            # Launch scheduler tick to poll for due jobs
            self._start_scheduler_tick()
            # Issue #3021: launch opt-in lifecycle loops. Both are no-op when
            # their policy is unconfigured; they poll on ``_is_running`` (set by
            # ``start()`` below) after an initial sleep, so starting them here is
            # safe. Idle-quiesce arms scale-to-zero; the drain watcher honours a
            # current-epoch external drain marker.
            if self._idle_policy is not None:
                self._lifecycle_task = asyncio.create_task(
                    self._run_idle_loop(), name="gateway-idle"
                )
            if self._drain_marker_policy is not None:
                self._drain_marker_task = asyncio.create_task(
                    self._run_drain_marker_watch(drain_timeout_cfg),
                    name="gateway-drain-marker",
                )
            await self.start()

        # Issue #2436: crash/shutdown forensics. Capture a fast, non-blocking
        # snapshot on a termination signal so the next boot (and the operator)
        # can see *why* the previous instance died (OOM vs supervisor stop vs
        # parent death). The snapshot/diagnostic never raise and never block
        # the asyncio teardown. A startup sanity check warns when the
        # supervisor's stop-timeout has less headroom than ``drain_timeout``.
        forensics_cfg = gw_cfg.get("forensics")
        if not isinstance(forensics_cfg, dict):
            forensics_cfg = {}
        # Normalise the toggle: env-substituted YAML (e.g. ``enabled:
        # ${FORENSICS_ENABLED}``) arrives as a string, so a raw truthiness
        # check would treat "false"/"0" as enabled. Default to enabled.
        forensics_enabled_raw = forensics_cfg.get("enabled", True)
        if isinstance(forensics_enabled_raw, str):
            forensics_enabled = (
                forensics_enabled_raw.strip().lower()
                in ("1", "true", "yes", "on")
            )
        else:
            forensics_enabled = bool(forensics_enabled_raw)
        diagnostic_dir = forensics_cfg.get("diagnostic_dir") or os.path.join(
            os.path.expanduser("~"), ".praisonai", "gateway", "forensics"
        )
        forensics = None
        if forensics_enabled:
            try:
                from .forensics import ShutdownForensics

                forensics = ShutdownForensics(
                    log_dir=diagnostic_dir, enabled=True
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Could not initialise shutdown forensics: %s", exc)
                forensics = None

        # Startup sanity check: warn (don't fail) when the supervisor would
        # likely kill us mid-drain with no explanation.
        if forensics is not None and drain_timeout_cfg and drain_timeout_cfg > 0:
            try:
                from praisonaiagents.gateway import drain_timeout_has_headroom

                stop_timeout_env = (
                    forensics_cfg.get("stop_timeout")
                    or os.environ.get("PRAISONAI_STOP_TIMEOUT")
                )
                stop_timeout = (
                    float(stop_timeout_env) if stop_timeout_env else None
                )
                if not drain_timeout_has_headroom(stop_timeout, drain_timeout_cfg):
                    logger.warning(
                        "Supervisor stop-timeout (%ss) < drain_timeout (%ss) "
                        "+ headroom; gateway may be killed mid-drain with no "
                        "explanation.",
                        stop_timeout,
                        drain_timeout_cfg,
                    )
            except (TypeError, ValueError, ImportError):
                pass

        # Register signal handlers for graceful shutdown using
        # loop.add_signal_handler (async-safe) with signal.signal fallback.
        import signal

        def _request_shutdown(
            signal_name: Optional[str] = None, forensic: bool = True
        ):
            # ``forensic`` is False on the raw ``signal.signal`` fallback path:
            # that callback runs in a C-signal context where re-entering
            # logging / subprocess could deadlock if a lock was held when the
            # signal arrived. There we only flip ``should_exit`` and let the
            # async path (when available) capture forensics. Keep *all* logging
            # behind this guard so the fallback never touches a logging lock.
            # Request drain FIRST so uvicorn always begins shutting down even
            # if the (best-effort) forensic logging / ``subprocess.Popen`` below
            # momentarily blocks under memory pressure or on a stuck host. This
            # guarantees we never miss the supervisor's drain window because of
            # diagnostics work.
            if self._server:
                self._server.should_exit = True
            if forensic:
                logger.info("Received shutdown signal, stopping gateway...")
            if forensic and forensics is not None:
                try:
                    from praisonaiagents.gateway import format_forensics_for_log

                    ctx = forensics.snapshot(signal_name=signal_name)
                    logger.warning(format_forensics_for_log(ctx))
                    forensics.spawn_diagnostic(ctx, diagnostic_dir)
                except Exception:  # pragma: no cover - never block teardown
                    pass

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            sig_name = sig.name
            try:
                loop.add_signal_handler(
                    sig, lambda n=sig_name: _request_shutdown(n, forensic=True)
                )
            except (NotImplementedError, OSError, ValueError):
                # Fallback for platforms where add_signal_handler is
                # unavailable. This runs in a C-signal context, so we must not
                # re-enter logging/subprocess: skip forensics here and only
                # request exit (forensic=False).
                try:
                    signal.signal(
                        sig,
                        lambda s, f, n=sig_name: _request_shutdown(
                            n, forensic=False
                        ),
                    )
                except (OSError, ValueError):
                    pass

        # Issue #2533: operator-triggered reload. SIGHUP triggers the same
        # diff-driven reload path as the file watcher, giving operators and
        # service managers (``systemctl reload``) a deterministic "reload now"
        # that never shuts the process down. SIGHUP does not exist on Windows,
        # so this is best-effort and skipped when unavailable.
        # ``reload_config`` serializes itself behind ``_reload_lock``, so a
        # SIGHUP that arrives mid-reload (from the watcher or a prior SIGHUP)
        # is queued and applied after the in-flight reload finishes rather
        # than interleaving channel mutations (Issue #2533).
        def _request_reload():
            logger.info("Received SIGHUP, reloading gateway config...")
            asyncio.ensure_future(self.reload_config(config_path))

        sighup = getattr(signal, "SIGHUP", None)
        if sighup is not None:
            try:
                loop.add_signal_handler(sighup, _request_reload)
            except (NotImplementedError, OSError, ValueError):
                pass

        try:
            await _run_all()
        finally:
            if self._config_watch_task:
                self._config_watch_task.cancel()
            if self._scheduler_task:
                self._scheduler_task.cancel()
            if self._cleanup_task:
                self._cleanup_task.cancel()
            # Issue #3021: stop lifecycle loops on shutdown.
            if self._lifecycle_task:
                self._lifecycle_task.cancel()
            if self._drain_marker_task:
                self._drain_marker_task.cancel()
            # Issue #2375: drain in-flight agent turns (channel bots) and
            # websocket sessions before final teardown when a drain timeout
            # is configured. The configured timeout bounds the *total*
            # shutdown drain: track elapsed across both phases so channel
            # bots + websocket sessions don't sum to 2 * drain_timeout.
            # No-op when unset (today's behaviour).
            drain_overall_start = time.monotonic()
            await self.stop_channels(drain_timeout=drain_timeout_cfg)
            if drain_timeout_cfg and drain_timeout_cfg > 0:
                remaining = drain_timeout_cfg - (time.monotonic() - drain_overall_start)
                if remaining > 0:
                    try:
                        await self._drain_active_sessions(
                            reason="shutdown", timeout=float(remaining)
                        )
                    except Exception as e:
                        logger.warning("Error draining websocket sessions: %s", e)
