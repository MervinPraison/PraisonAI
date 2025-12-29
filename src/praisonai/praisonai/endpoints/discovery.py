"""
Unified Discovery Schema

Provides versioned discovery document format for all PraisonAI serve features.
This schema is consistent across all provider types.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from enum import Enum


# Schema version - increment on breaking changes
SCHEMA_VERSION = "1.0.0"


class ProviderType(str, Enum):
    """Supported provider types."""
    RECIPE = "recipe"
    AGENTS_API = "agents-api"
    MCP = "mcp"
    TOOLS_MCP = "tools-mcp"
    A2A = "a2a"
    A2U = "a2u"


class StreamingMode(str, Enum):
    """Supported streaming modes."""
    NONE = "none"
    SSE = "sse"
    WEBSOCKET = "websocket"
    MCP_STREAM = "mcp-stream"


class AuthMode(str, Enum):
    """Supported authentication modes."""
    NONE = "none"
    API_KEY = "api-key"
    BEARER = "bearer"
    JWT = "jwt"


@dataclass
class EndpointInfo:
    """Information about a single endpoint."""
    name: str
    description: str = ""
    provider_type: str = "recipe"
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    
    # Schema information
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    
    # Capabilities
    streaming: List[str] = field(default_factory=lambda: ["none"])
    auth_modes: List[str] = field(default_factory=lambda: ["none"])
    
    # Metadata
    examples: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ProviderInfo:
    """Information about a provider."""
    type: str
    name: str
    version: str = "1.0.0"
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class DiscoveryDocument:
    """
    Unified discovery document for PraisonAI servers.
    
    This document is served at /__praisonai__/discovery and provides
    a consistent interface for discovering endpoints across all provider types.
    """
    schema_version: str = SCHEMA_VERSION
    server_name: str = "praisonai"
    server_version: str = "1.0.0"
    
    # Provider information
    providers: List[ProviderInfo] = field(default_factory=list)
    
    # Endpoint information
    endpoints: List[EndpointInfo] = field(default_factory=list)
    
    # Server capabilities
    auth_modes: List[str] = field(default_factory=lambda: ["none"])
    streaming_modes: List[str] = field(default_factory=lambda: ["none", "sse"])
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "schema_version": self.schema_version,
            "server_name": self.server_name,
            "server_version": self.server_version,
            "providers": [p.to_dict() for p in self.providers],
            "endpoints": [e.to_dict() for e in self.endpoints],
            "auth_modes": self.auth_modes,
            "streaming_modes": self.streaming_modes,
            "metadata": self.metadata,
        }
    
    def add_provider(self, provider: ProviderInfo) -> None:
        """Add a provider to the discovery document."""
        self.providers.append(provider)
    
    def add_endpoint(self, endpoint: EndpointInfo) -> None:
        """Add an endpoint to the discovery document."""
        self.endpoints.append(endpoint)
    
    def get_endpoints_by_type(self, provider_type: str) -> List[EndpointInfo]:
        """Get endpoints filtered by provider type."""
        return [e for e in self.endpoints if e.provider_type == provider_type]
    
    def get_endpoint_by_name(self, name: str) -> Optional[EndpointInfo]:
        """Get an endpoint by name."""
        for e in self.endpoints:
            if e.name == name:
                return e
        return None


def create_discovery_document(
    server_name: str = "praisonai",
    server_version: Optional[str] = None,
) -> DiscoveryDocument:
    """
    Create a new discovery document.
    
    Args:
        server_name: Name of the server
        server_version: Version of the server (auto-detected if not provided)
        
    Returns:
        DiscoveryDocument instance
    """
    if server_version is None:
        try:
            from praisonai.version import __version__
            server_version = __version__
        except ImportError:
            server_version = "unknown"
    
    return DiscoveryDocument(
        server_name=server_name,
        server_version=server_version,
    )
