"""
MCP Transport Abstraction Layer.

This module provides a common interface for all MCP transports,
enabling easy switching between transport types and custom
transport implementations.

Transport types:
- stdio: Standard input/output (subprocess)
- sse: Server-Sent Events (legacy HTTP+SSE)
- http_stream: Streamable HTTP (current standard)
- websocket: WebSocket (SEP-1288)
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Type
from dataclasses import dataclass, field


@dataclass
class TransportConfig:
    """
    Configuration for MCP transports.
    
    Attributes:
        timeout: Connection/operation timeout in seconds
        debug: Enable debug logging
        retry_count: Number of retry attempts
        retry_delay: Base delay between retries in seconds
        auth_token: Optional authentication token
        headers: Additional headers for HTTP transports
    """
    timeout: int = 60
    debug: bool = False
    retry_count: int = 3
    retry_delay: float = 1.0
    auth_token: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)


class BaseTransport(ABC):
    """
    Abstract base class for MCP transports.
    
    All MCP transports must implement this interface to ensure
    consistent behavior across transport types.
    
    The transport is responsible for:
    - Establishing and maintaining connections
    - Sending JSON-RPC messages
    - Receiving JSON-RPC messages
    - Proper cleanup on close
    """
    
    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to the MCP server.
        
        Raises:
            ConnectionError: If connection fails
        """
        pass
    
    @abstractmethod
    async def send(self, message: Dict[str, Any]) -> None:
        """
        Send a JSON-RPC message to the server.
        
        Args:
            message: JSON-RPC message dictionary
            
        Raises:
            RuntimeError: If not connected
        """
        pass
    
    @abstractmethod
    async def receive(self) -> Dict[str, Any]:
        """
        Receive a JSON-RPC message from the server.
        
        Returns:
            JSON-RPC message dictionary
            
        Raises:
            RuntimeError: If not connected
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the connection and cleanup resources.
        """
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if transport is currently connected."""
        pass
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


def get_transport_type(target: str) -> str:
    """
    Determine the appropriate transport type for a target.
    
    Args:
        target: URL or command string
        
    Returns:
        Transport type string: "stdio", "sse", "http_stream", or "websocket"
    """
    if not isinstance(target, str):
        return "stdio"
    
    # WebSocket URLs
    if re.match(r'^wss?://', target, re.IGNORECASE):
        return "websocket"
    
    # HTTP URLs
    if re.match(r'^https?://', target, re.IGNORECASE):
        # Legacy SSE endpoint
        if target.endswith('/sse'):
            return "sse"
        # Default to Streamable HTTP
        return "http_stream"
    
    # Everything else is stdio (command)
    return "stdio"


class TransportRegistry:
    """
    Registry for MCP transport implementations.
    
    This allows registration of custom transports and provides
    a central place to look up transport classes by name.
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._transports: Dict[str, Type[BaseTransport]] = {}
    
    def register(self, name: str, transport_class: Type[BaseTransport]) -> None:
        """
        Register a transport class.
        
        Args:
            name: Transport name (e.g., "websocket")
            transport_class: Transport class (must extend BaseTransport)
        """
        if not issubclass(transport_class, BaseTransport):
            raise TypeError(f"{transport_class} must extend BaseTransport")
        self._transports[name] = transport_class
    
    def get(self, name: str) -> Optional[Type[BaseTransport]]:
        """
        Get a registered transport class.
        
        Args:
            name: Transport name
            
        Returns:
            Transport class or None if not found
        """
        return self._transports.get(name)
    
    def list_transports(self) -> List[str]:
        """
        List all registered transport names.
        
        Returns:
            List of transport names
        """
        return list(self._transports.keys())
    
    def unregister(self, name: str) -> None:
        """
        Unregister a transport.
        
        Args:
            name: Transport name to remove
        """
        self._transports.pop(name, None)


# Placeholder transport classes for registry
# These are minimal implementations to satisfy the registry

class StdioTransportPlaceholder(BaseTransport):
    """Placeholder for stdio transport."""
    async def connect(self): pass
    async def send(self, message): pass
    async def receive(self): return {}
    async def close(self): pass
    @property
    def is_connected(self): return False


class SSETransportPlaceholder(BaseTransport):
    """Placeholder for SSE transport."""
    async def connect(self): pass
    async def send(self, message): pass
    async def receive(self): return {}
    async def close(self): pass
    @property
    def is_connected(self): return False


class HTTPStreamTransportPlaceholder(BaseTransport):
    """Placeholder for HTTP Stream transport."""
    async def connect(self): pass
    async def send(self, message): pass
    async def receive(self): return {}
    async def close(self): pass
    @property
    def is_connected(self): return False


class WebSocketTransportPlaceholder(BaseTransport):
    """Placeholder for WebSocket transport."""
    async def connect(self): pass
    async def send(self, message): pass
    async def receive(self): return {}
    async def close(self): pass
    @property
    def is_connected(self): return False


# Default registry instance
_default_registry: Optional[TransportRegistry] = None


def get_default_registry() -> TransportRegistry:
    """
    Get the default transport registry with built-in transports.
    
    Returns:
        TransportRegistry with default transports registered
    """
    global _default_registry
    
    if _default_registry is None:
        _default_registry = TransportRegistry()
        
        # Register default transports
        _default_registry.register("stdio", StdioTransportPlaceholder)
        _default_registry.register("sse", SSETransportPlaceholder)
        _default_registry.register("http_stream", HTTPStreamTransportPlaceholder)
        _default_registry.register("websocket", WebSocketTransportPlaceholder)
    
    return _default_registry


def create_transport(
    target: str,
    config: Optional[TransportConfig] = None,
    registry: Optional[TransportRegistry] = None
) -> BaseTransport:
    """
    Create a transport instance for the given target.
    
    Args:
        target: URL or command string
        config: Optional transport configuration
        registry: Optional custom registry (uses default if None)
        
    Returns:
        Transport instance
        
    Raises:
        ValueError: If no suitable transport found
    """
    if registry is None:
        registry = get_default_registry()
    
    if config is None:
        config = TransportConfig()
    
    transport_type = get_transport_type(target)
    transport_class = registry.get(transport_type)
    
    if transport_class is None:
        raise ValueError(f"No transport registered for type: {transport_type}")
    
    return transport_class()
