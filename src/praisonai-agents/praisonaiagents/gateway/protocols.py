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
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Union,
    runtime_checkable,
)

if TYPE_CHECKING:
    from ..agent import Agent


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
    """
    
    type: Union[EventType, str]
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    target: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "data": self.data,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "target": self.target,
        }
    
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
    """
    
    content: Union[str, Dict[str, Any]]
    sender_id: str
    session_id: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "content": self.content,
            "sender_id": self.sender_id,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "reply_to": self.reply_to,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GatewayMessage":
        """Create from dictionary."""
        return cls(
            content=data.get("content", ""),
            sender_id=data.get("sender_id", "unknown"),
            session_id=data.get("session_id", "default"),
            message_id=data.get("message_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            reply_to=data.get("reply_to"),
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
    
    def add_pending(
        self, 
        channel_type: str, 
        channel_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a new pairing code for a channel.
        
        Args:
            channel_type: Type of channel (e.g., "telegram", "slack", "ui")
            channel_id: Optional channel identifier
            metadata: Optional metadata for the pairing request
            
        Returns:
            The generated pairing code
        """
        ...
    
    def approve(
        self, 
        code: str, 
        channel_id: str, 
        channel_type: str, 
        label: str = ""
    ) -> bool:
        """Approve a pairing code, authorizing the channel.
        
        Args:
            code: The pairing code to approve
            channel_id: Channel identifier
            channel_type: Type of channel
            label: Optional human-readable label
            
        Returns:
            True if approval successful, False if code invalid/expired
        """
        ...
    
    def is_paired(self, channel_type: str, channel_id: str) -> bool:
        """Check if a channel is authorized.
        
        Args:
            channel_type: Type of channel
            channel_id: Channel identifier
            
        Returns:
            True if channel is paired/authorized
        """
        ...
    
    def list_paired(self) -> List[Dict[str, Any]]:
        """List all authorized channels.
        
        Returns:
            List of paired channel information
        """
        ...
    
    def revoke(self, channel_type: str, channel_id: str) -> bool:
        """Revoke authorization for a channel.
        
        Args:
            channel_type: Type of channel
            channel_id: Channel identifier
            
        Returns:
            True if revocation successful, False if not found
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
