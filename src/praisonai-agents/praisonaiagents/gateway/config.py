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


@dataclass
class GatewayConfig:
    """Configuration for the gateway server.
    
    Attributes:
        host: Host to bind to
        port: Port to listen on
        cors_origins: Allowed CORS origins
        auth_token: Optional authentication token
        max_connections: Maximum concurrent connections
        max_sessions_per_agent: Maximum sessions per agent (0 = unlimited)
        session_config: Default session configuration
        heartbeat_interval: Heartbeat interval in seconds
        reconnect_timeout: Time to wait for reconnection before closing session
        ssl_cert: Path to SSL certificate (for HTTPS/WSS)
        ssl_key: Path to SSL key
    """
    
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    auth_token: Optional[str] = None
    max_connections: int = 1000
    max_sessions_per_agent: int = 0  # 0 = unlimited
    session_config: SessionConfig = field(default_factory=SessionConfig)
    heartbeat_interval: int = 30
    reconnect_timeout: int = 60
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (hides sensitive data)."""
        return {
            "host": self.host,
            "port": self.port,
            "cors_origins": self.cors_origins,
            "auth_token": "***" if self.auth_token else None,
            "max_connections": self.max_connections,
            "max_sessions_per_agent": self.max_sessions_per_agent,
            "session_config": self.session_config.to_dict(),
            "heartbeat_interval": self.heartbeat_interval,
            "reconnect_timeout": self.reconnect_timeout,
            "ssl_enabled": bool(self.ssl_cert and self.ssl_key),
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
            cors_origins=gw_data.get("cors_origins", ["*"]),
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
