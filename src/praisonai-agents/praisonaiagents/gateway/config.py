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
