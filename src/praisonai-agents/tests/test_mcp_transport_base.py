"""Tests for MCP Transport Abstraction Layer - TDD approach.

These tests define the expected behavior of the transport abstraction
layer that provides a common interface for all MCP transports.

Transport abstraction features:
- BaseTransport abstract class
- Common interface (connect, send, receive, close)
- Transport factory for automatic selection
"""

import pytest
from abc import ABC


class TestBaseTransport:
    """Test BaseTransport abstract class."""
    
    def test_base_transport_is_abstract(self):
        """Test that BaseTransport cannot be instantiated directly."""
        from praisonaiagents.mcp.mcp_transport import BaseTransport
        
        with pytest.raises(TypeError):
            BaseTransport()
    
    def test_base_transport_defines_interface(self):
        """Test that BaseTransport defines required interface methods."""
        from praisonaiagents.mcp.mcp_transport import BaseTransport
        import inspect
        
        # Check required abstract methods exist
        assert hasattr(BaseTransport, 'connect')
        assert hasattr(BaseTransport, 'send')
        assert hasattr(BaseTransport, 'receive')
        assert hasattr(BaseTransport, 'close')
        assert hasattr(BaseTransport, 'is_connected')
    
    def test_concrete_transport_must_implement_interface(self):
        """Test that concrete transports must implement all methods."""
        from praisonaiagents.mcp.mcp_transport import BaseTransport
        
        # Incomplete implementation should fail
        class IncompleteTransport(BaseTransport):
            pass
        
        with pytest.raises(TypeError):
            IncompleteTransport()


class TestTransportFactory:
    """Test transport factory for automatic selection."""
    
    def test_factory_selects_stdio_for_command(self):
        """Test factory selects stdio transport for command strings."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("python /path/to/server.py") == "stdio"
        assert get_transport_type("npx @modelcontextprotocol/server") == "stdio"
    
    def test_factory_selects_websocket_for_ws_url(self):
        """Test factory selects WebSocket transport for ws:// URLs."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("ws://localhost:8080/mcp") == "websocket"
        assert get_transport_type("wss://example.com/mcp") == "websocket"
    
    def test_factory_selects_sse_for_sse_url(self):
        """Test factory selects SSE transport for /sse URLs."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("http://localhost:8080/sse") == "sse"
        assert get_transport_type("https://example.com/sse") == "sse"
    
    def test_factory_selects_http_stream_for_http_url(self):
        """Test factory selects HTTP Stream transport for HTTP URLs."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("http://localhost:8080/mcp") == "http_stream"
        assert get_transport_type("https://example.com/mcp") == "http_stream"


class TestTransportConfig:
    """Test transport configuration."""
    
    def test_transport_config_creation(self):
        """Test TransportConfig can be created."""
        from praisonaiagents.mcp.mcp_transport import TransportConfig
        
        config = TransportConfig(
            timeout=30,
            debug=True,
            retry_count=3
        )
        
        assert config.timeout == 30
        assert config.debug is True
        assert config.retry_count == 3
    
    def test_transport_config_defaults(self):
        """Test TransportConfig has sensible defaults."""
        from praisonaiagents.mcp.mcp_transport import TransportConfig
        
        config = TransportConfig()
        
        assert config.timeout == 60  # Default timeout
        assert config.debug is False
        assert config.retry_count == 3


class TestTransportRegistry:
    """Test transport registration mechanism."""
    
    def test_register_custom_transport(self):
        """Test registering a custom transport."""
        from praisonaiagents.mcp.mcp_transport import (
            TransportRegistry, BaseTransport
        )
        
        class CustomTransport(BaseTransport):
            async def connect(self): pass
            async def send(self, message): pass
            async def receive(self): pass
            async def close(self): pass
            @property
            def is_connected(self): return False
        
        registry = TransportRegistry()
        registry.register("custom", CustomTransport)
        
        assert "custom" in registry.list_transports()
    
    def test_get_registered_transport(self):
        """Test getting a registered transport class."""
        from praisonaiagents.mcp.mcp_transport import (
            TransportRegistry, BaseTransport
        )
        
        class MyTransport(BaseTransport):
            async def connect(self): pass
            async def send(self, message): pass
            async def receive(self): pass
            async def close(self): pass
            @property
            def is_connected(self): return False
        
        registry = TransportRegistry()
        registry.register("my_transport", MyTransport)
        
        transport_class = registry.get("my_transport")
        assert transport_class is MyTransport
    
    def test_default_transports_registered(self):
        """Test that default transports are pre-registered."""
        from praisonaiagents.mcp.mcp_transport import get_default_registry
        
        registry = get_default_registry()
        transports = registry.list_transports()
        
        # Default transports should be available
        assert "stdio" in transports
        assert "sse" in transports
        assert "http_stream" in transports
        assert "websocket" in transports


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
