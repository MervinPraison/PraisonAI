"""
Configuration schema for PraisonAI CLI.

Defines the structure and defaults for configuration.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Literal


@dataclass
class OutputConfig:
    """Output configuration."""
    format: str = "text"  # text, json, stream-json
    color: bool = True
    verbose: bool = False
    quiet: bool = False
    screen_reader: bool = False


@dataclass
class TracesConfig:
    """Traces configuration."""
    enabled: bool = False
    endpoint: Optional[str] = None
    sample_rate: float = 1.0


@dataclass
class MCPOAuthConfig:
    """OAuth configuration for remote MCP servers."""
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scopes: List[str] = field(default_factory=list)


@dataclass
class MCPLocalConfig:
    """Local MCP server configuration (stdio transport)."""
    type: Literal["local"] = "local"
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout: int = 60000  # milliseconds


@dataclass
class MCPRemoteConfig:
    """Remote MCP server configuration (HTTP/WebSocket transport)."""
    type: Literal["remote"] = "remote"
    url: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    oauth: Optional[MCPOAuthConfig] = None
    enabled: bool = True
    timeout: int = 30000  # milliseconds


# Union type for MCP server configs
MCPServerConfig = Union[MCPLocalConfig, MCPRemoteConfig]


@dataclass
class MCPConfig:
    """MCP configuration."""
    servers: Dict[str, MCPServerConfig] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Model configuration."""
    default: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 16000


@dataclass
class SessionConfig:
    """Session configuration."""
    auto_save: bool = False
    history_limit: int = 10


@dataclass
class ConfigSchema:
    """
    Complete configuration schema.
    
    Represents all configurable options for PraisonAI CLI.
    """
    output: OutputConfig = field(default_factory=OutputConfig)
    traces: TracesConfig = field(default_factory=TracesConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    
    # Additional settings stored as dict for flexibility
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "output": {
                "format": self.output.format,
                "color": self.output.color,
                "verbose": self.output.verbose,
                "quiet": self.output.quiet,
                "screen_reader": self.output.screen_reader,
            },
            "traces": {
                "enabled": self.traces.enabled,
                "endpoint": self.traces.endpoint,
                "sample_rate": self.traces.sample_rate,
            },
            "mcp": {
                "servers": {
                    name: self._server_to_dict(server)
                    for name, server in self.mcp.servers.items()
                }
            },
            "model": {
                "default": self.model.default,
                "temperature": self.model.temperature,
                "max_tokens": self.model.max_tokens,
            },
            "session": {
                "auto_save": self.session.auto_save,
                "history_limit": self.session.history_limit,
            },
            **self.extra,
        }
    
    def _server_to_dict(self, server: MCPServerConfig) -> Dict[str, Any]:
        """Convert MCP server config to dictionary."""
        if isinstance(server, MCPRemoteConfig):
            result = {
                "type": "remote",
                "url": server.url,
                "headers": server.headers,
                "enabled": server.enabled,
                "timeout": server.timeout,
            }
            if server.oauth:
                result["oauth"] = {
                    "client_id": server.oauth.client_id,
                    "client_secret": server.oauth.client_secret,
                    "scopes": server.oauth.scopes,
                }
            return result
        else:
            # MCPLocalConfig
            return {
                "type": "local",
                "command": server.command,
                "args": server.args,
                "env": server.env,
                "enabled": server.enabled,
                "timeout": server.timeout,
            }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigSchema":
        """Create from dictionary."""
        output_data = data.get("output", {})
        traces_data = data.get("traces", {})
        mcp_data = data.get("mcp", {})
        model_data = data.get("model", {})
        session_data = data.get("session", {})
        
        # Extract known keys
        known_keys = {"output", "traces", "mcp", "model", "session"}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        
        # Parse MCP servers
        mcp_servers = {}
        for name, server_data in mcp_data.get("servers", {}).items():
            server_type = server_data.get("type", "local")
            if server_type == "remote":
                oauth_data = server_data.get("oauth")
                oauth_config = None
                if oauth_data and isinstance(oauth_data, dict):
                    oauth_config = MCPOAuthConfig(
                        client_id=oauth_data.get("client_id"),
                        client_secret=oauth_data.get("client_secret"),
                        scopes=oauth_data.get("scopes", []),
                    )
                mcp_servers[name] = MCPRemoteConfig(
                    type="remote",
                    url=server_data.get("url", ""),
                    headers=server_data.get("headers", {}),
                    oauth=oauth_config,
                    enabled=server_data.get("enabled", True),
                    timeout=server_data.get("timeout", 30000),
                )
            else:
                mcp_servers[name] = MCPLocalConfig(
                    type="local",
                    command=server_data.get("command", ""),
                    args=server_data.get("args", []),
                    env=server_data.get("env", {}),
                    enabled=server_data.get("enabled", True),
                    timeout=server_data.get("timeout", 60000),
                )
        
        return cls(
            output=OutputConfig(
                format=output_data.get("format", "text"),
                color=output_data.get("color", True),
                verbose=output_data.get("verbose", False),
                quiet=output_data.get("quiet", False),
                screen_reader=output_data.get("screen_reader", False),
            ),
            traces=TracesConfig(
                enabled=traces_data.get("enabled", False),
                endpoint=traces_data.get("endpoint"),
                sample_rate=traces_data.get("sample_rate", 1.0),
            ),
            mcp=MCPConfig(servers=mcp_servers),
            model=ModelConfig(
                default=model_data.get("default", "gpt-4o-mini"),
                temperature=model_data.get("temperature", 0.7),
                max_tokens=model_data.get("max_tokens", 16000),
            ),
            session=SessionConfig(
                auto_save=session_data.get("auto_save", False),
                history_limit=session_data.get("history_limit", 10),
            ),
            extra=extra,
        )


# Default configuration
DEFAULT_CONFIG = ConfigSchema()
