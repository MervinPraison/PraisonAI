"""
Gateway Protocols for PraisonAI Agents.

Defines the interfaces for gateway/control plane implementations.
These protocols enable multi-agent coordination, session management,
and real-time communication.

All implementations should live in the praisonai wrapper package.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
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
    
    Example usage (implementation in praisonai wrapper):
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
    
    Example usage (implementation in praisonai wrapper):
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

    Example usage (implementation in praisonai wrapper)::

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
