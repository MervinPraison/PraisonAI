"""
Gateway Configuration for PraisonAI Agents.

Provides configuration dataclasses for gateway and session settings.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SessionConfig:
    """Configuration for gateway sessions.
    
    Attributes:
        timeout: Session timeout in seconds (0 = no timeout)
        max_messages: Maximum messages to keep in history (0 = unlimited)
        persist: Whether to persist session state
        persist_path: Path for session persistence
        metadata: Additional session metadata
    """
    
    timeout: int = 3600  # 1 hour default
    max_messages: int = 1000
    persist: bool = False
    persist_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timeout": self.timeout,
            "max_messages": self.max_messages,
            "persist": self.persist,
            "persist_path": self.persist_path,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Push notification configuration
# ---------------------------------------------------------------------------

@dataclass
class RedisConfig:
    """Redis connection configuration for push service scaling.
    
    Attributes:
        url: Full Redis URL (takes precedence over host/port)
        host: Redis host
        port: Redis port
        db: Redis database number
        password: Redis password
        prefix: Key prefix namespace
        max_connections: Connection pool size
    """
    
    url: Optional[str] = None
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    prefix: str = "praison:push:"
    max_connections: int = 20
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "url": "***" if self.url else None,
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "password": "***" if self.password else None,
            "prefix": self.prefix,
            "max_connections": self.max_connections,
        }


@dataclass
class PresenceConfig:
    """Configuration for presence tracking.
    
    Attributes:
        enabled: Toggle presence tracking
        heartbeat_interval: Expected heartbeat frequency from clients (seconds)
        offline_timeout: Mark offline after this many seconds without heartbeat
        broadcast_changes: Broadcast presence changes to subscribed channels
    """
    
    enabled: bool = True
    heartbeat_interval: int = 15
    offline_timeout: int = 45
    broadcast_changes: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "heartbeat_interval": self.heartbeat_interval,
            "offline_timeout": self.offline_timeout,
            "broadcast_changes": self.broadcast_changes,
        }


@dataclass
class DeliveryConfig:
    """Configuration for at-least-once delivery guarantees.
    
    Attributes:
        enabled: Toggle delivery guarantees
        ack_timeout: Seconds to wait for ACK before retrying
        max_retries: Maximum retry attempts
        retry_backoff: Exponential backoff multiplier
        message_ttl: How long to retain unacknowledged messages (seconds)
        store_backend: Message store backend ("memory" or "redis")
    """
    
    enabled: bool = True
    ack_timeout: int = 30
    max_retries: int = 3
    retry_backoff: float = 2.0
    message_ttl: int = 86400
    store_backend: str = "memory"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "ack_timeout": self.ack_timeout,
            "max_retries": self.max_retries,
            "retry_backoff": self.retry_backoff,
            "message_ttl": self.message_ttl,
            "store_backend": self.store_backend,
        }


@dataclass
class PollingConfig:
    """Configuration for HTTP long-polling fallback.
    
    Attributes:
        enabled: Toggle polling fallback
        long_poll_timeout: Long-poll hang duration (seconds)
        max_batch_size: Max messages per poll response
    """
    
    enabled: bool = True
    long_poll_timeout: int = 30
    max_batch_size: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "long_poll_timeout": self.long_poll_timeout,
            "max_batch_size": self.max_batch_size,
        }


@dataclass
class PushConfig:
    """Top-level configuration for the push notification service.
    
    All push capabilities are opt-in. When enabled=False (default),
    zero overhead is added to the gateway.
    
    Attributes:
        enabled: Feature toggle (push is opt-in)
        redis: Redis config for cross-server scaling (None = local-only)
        presence: Presence tracking settings
        delivery: Delivery guarantee settings
        polling: Polling fallback settings
    """
    
    enabled: bool = False
    redis: Optional[RedisConfig] = None
    presence: PresenceConfig = field(default_factory=PresenceConfig)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "redis": self.redis.to_dict() if self.redis else None,
            "presence": self.presence.to_dict(),
            "delivery": self.delivery.to_dict(),
            "polling": self.polling.to_dict(),
        }


@dataclass
class GatewayConfig:
    """Configuration for the gateway server.
    
    Attributes:
        host: Host to bind to
        port: Port to listen on
        cors_origins: Allowed CORS origins
        allowed_origins: Allowed origins for WebSocket connections (CSWSH defense)
        auth_token: Optional authentication token
        max_connections: Maximum concurrent connections
        max_sessions_per_agent: Maximum sessions per agent (0 = unlimited)
        session_config: Default session configuration
        heartbeat_interval: Heartbeat interval in seconds
        reconnect_timeout: Time to wait for reconnection before closing session
        ssl_cert: Path to SSL certificate (for HTTPS/WSS)
        ssl_key: Path to SSL key
        push: Push notification service configuration
    """
    
    host: str = "127.0.0.1"
    port: int = 8765
    bind_host: Optional[str] = None
    cors_origins: List[str] = field(default_factory=lambda: [])
    allowed_origins: List[str] = field(default_factory=lambda: [])
    auth_token: Optional[str] = None
    max_connections: int = 1000
    max_sessions_per_agent: int = 0  # 0 = unlimited
    session_config: SessionConfig = field(default_factory=SessionConfig)
    heartbeat_interval: int = 30
    reconnect_timeout: int = 60
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    push: PushConfig = field(default_factory=PushConfig)

    def __post_init__(self) -> None:
        """Post-initialization to set bind_host from host if not specified."""
        if self.bind_host is None:
            self.bind_host = self.host
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "host": self.host,
            "port": self.port,
            "cors_origins": self.cors_origins,
            "allowed_origins": self.allowed_origins,
            "auth_token": "***" if self.auth_token else None,
            "max_connections": self.max_connections,
            "max_sessions_per_agent": self.max_sessions_per_agent,
            "session_config": self.session_config.to_dict(),
            "heartbeat_interval": self.heartbeat_interval,
            "reconnect_timeout": self.reconnect_timeout,
            "ssl_enabled": bool(self.ssl_cert and self.ssl_key),
            "push": self.push.to_dict(),
        }
    
    @property
    def is_secure(self) -> bool:
        """Whether SSL/TLS is enabled."""
        return bool(self.ssl_cert and self.ssl_key)
    
    @property
    def ws_url(self) -> str:
        """WebSocket URL for this gateway."""
        protocol = "wss" if self.is_secure else "ws"
        return f"{protocol}://{self.host}:{self.port}"
    
    @property
    def http_url(self) -> str:
        """HTTP URL for this gateway."""
        protocol = "https" if self.is_secure else "http"
        return f"{protocol}://{self.host}:{self.port}"


@dataclass
class ChannelRouteConfig:
    """Configuration for routing channel messages to agents.
    
    Attributes:
        channel_type: Platform name (telegram, discord, slack, etc.)
        token_env: Environment variable name for the channel token
        app_token_env: Optional env var for app token (Slack Socket Mode)
        routes: Mapping of context → agent_id
                Keys: "dm", "group", "channel", "default"
                Values: agent ID strings
        enabled: Whether this channel is enabled
        metadata: Additional channel-specific configuration
    """
    
    channel_type: str
    token_env: str = ""
    app_token_env: Optional[str] = None
    routes: Dict[str, str] = field(default_factory=lambda: {"default": "default"})
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_agent_id(self, context: str = "default") -> str:
        """Resolve agent ID for a given message context.
        
        Args:
            context: Message context (dm, group, channel, default)
            
        Returns:
            The agent ID for the given context, falling back to "default" route.
        """
        return self.routes.get(context, self.routes.get("default", "default"))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "channel_type": self.channel_type,
            "token_env": self.token_env,
            "app_token_env": self.app_token_env,
            "routes": dict(self.routes),
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChannelRouteConfig":
        """Create from dictionary."""
        return cls(
            channel_type=data.get("channel_type", ""),
            token_env=data.get("token_env", ""),
            app_token_env=data.get("app_token_env"),
            routes=data.get("routes", {"default": "default"}),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )


@dataclass
class MultiChannelGatewayConfig:
    """Configuration for multi-channel gateway mode.
    
    Loaded from gateway.yaml. Defines agents, channels, and routing.
    
    Attributes:
        gateway: Base gateway configuration
        agents: Agent configurations by ID (name → config dict)
        channels: Channel routing configurations by name
    """
    
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    agents: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    channels: Dict[str, ChannelRouteConfig] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiChannelGatewayConfig":
        """Create from parsed YAML dictionary.
        
        Expected format::
        
            gateway:
              host: "127.0.0.1"
              port: 8765
            agents:
              personal:
                instructions: "You are a helpful assistant"
                model: gpt-4o-mini
            channels:
              telegram:
                token: ${TELEGRAM_BOT_TOKEN}
                routes:
                  dm: personal
                  default: personal
        
        Args:
            data: Parsed YAML dictionary
            
        Returns:
            Configured MultiChannelGatewayConfig instance
        """
        # Parse gateway section
        gw_data = data.get("gateway", {})
        gateway_config = GatewayConfig(
            host=gw_data.get("host", "127.0.0.1"),
            port=gw_data.get("port", 8765),
            cors_origins=gw_data.get("cors_origins", []),
            allowed_origins=gw_data.get("allowed_origins", []),
            auth_token=gw_data.get("auth_token"),
            max_connections=gw_data.get("max_connections", 1000),
        )
        
        # Parse agents section (pass through as dicts)
        agents = data.get("agents", {})
        
        # Parse channels section
        channels: Dict[str, ChannelRouteConfig] = {}
        for name, ch_data in data.get("channels", {}).items():
            if isinstance(ch_data, dict):
                channels[name] = ChannelRouteConfig(
                    channel_type=name,
                    token_env=ch_data.get("token", ""),
                    app_token_env=ch_data.get("app_token"),
                    routes=ch_data.get("routes", {"default": "default"}),
                    enabled=ch_data.get("enabled", True),
                    metadata={
                        k: v for k, v in ch_data.items()
                        if k not in ("token", "app_token", "routes", "enabled")
                    },
                )
        
        return cls(
            gateway=gateway_config,
            agents=agents,
            channels=channels,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gateway": self.gateway.to_dict(),
            "agents": dict(self.agents),
            "channels": {
                name: ch.to_dict() for name, ch in self.channels.items()
            },
        }
