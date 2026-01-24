"""Tests for MCP WebSocket Transport - TDD approach.

These tests define the expected behavior of the WebSocket transport module.
WebSocket transport is an optional feature that requires the 'websockets' package.

Performance considerations:
- WebSocket is lazy-loaded only when ws:// or wss:// URLs are used
- No impact on existing stdio/SSE/HTTP transports
- Uses asyncio for non-blocking I/O
"""

import pytest
from unittest.mock import Mock


# Skip all tests if websockets is not installed
pytest.importorskip("websockets", reason="websockets package not installed")


class TestWebSocketURLDetection:
    """Test URL detection for WebSocket transport."""
    
    def test_detects_ws_url(self):
        """Test that ws:// URLs are detected as WebSocket."""
        from praisonaiagents.mcp.mcp_websocket import is_websocket_url
        
        assert is_websocket_url("ws://localhost:8080") is True
        assert is_websocket_url("ws://example.com/mcp") is True
        assert is_websocket_url("ws://127.0.0.1:3000/ws") is True
    
    def test_detects_wss_url(self):
        """Test that wss:// URLs are detected as WebSocket (secure)."""
        from praisonaiagents.mcp.mcp_websocket import is_websocket_url
        
        assert is_websocket_url("wss://localhost:8080") is True
        assert is_websocket_url("wss://example.com/mcp") is True
        assert is_websocket_url("wss://secure.server.com:443/ws") is True
    
    def test_rejects_http_urls(self):
        """Test that HTTP URLs are not detected as WebSocket."""
        from praisonaiagents.mcp.mcp_websocket import is_websocket_url
        
        assert is_websocket_url("http://localhost:8080") is False
        assert is_websocket_url("https://example.com/mcp") is False
        assert is_websocket_url("http://localhost:8080/sse") is False
    
    def test_rejects_non_url_strings(self):
        """Test that non-URL strings are not detected as WebSocket."""
        from praisonaiagents.mcp.mcp_websocket import is_websocket_url
        
        assert is_websocket_url("python") is False
        assert is_websocket_url("/path/to/script.py") is False
        assert is_websocket_url("npx @modelcontextprotocol/server") is False


class TestWebSocketMCPTool:
    """Test WebSocketMCPTool wrapper class."""
    
    def test_tool_has_required_attributes(self):
        """Test that tool wrapper has all required attributes for Agent."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketMCPTool
        
        mock_session = Mock()
        tool = WebSocketMCPTool(
            name="test_tool",
            description="A test tool",
            session=mock_session,
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}}
        )
        
        assert tool.name == "test_tool"
        assert tool.__name__ == "test_tool"
        assert tool.__qualname__ == "test_tool"
        assert tool.__doc__ == "A test tool"
        assert tool.description == "A test tool"
        assert hasattr(tool, '__signature__')
    
    def test_tool_generates_correct_signature(self):
        """Test that tool generates correct function signature from schema."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketMCPTool
        import inspect
        
        mock_session = Mock()
        tool = WebSocketMCPTool(
            name="search",
            description="Search tool",
            session=mock_session,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"}
                },
                "required": ["query"]
            }
        )
        
        sig = tool.__signature__
        params = list(sig.parameters.keys())
        
        assert "query" in params
        assert "max_results" in params
        assert sig.parameters["query"].default == inspect.Parameter.empty
        assert sig.parameters["max_results"].default is None  # Optional
    
    def test_tool_converts_to_openai_format(self):
        """Test conversion to OpenAI tool format."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketMCPTool
        
        mock_session = Mock()
        tool = WebSocketMCPTool(
            name="search",
            description="Search the web",
            session=mock_session,
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        )
        
        openai_tool = tool.to_openai_tool()
        
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "search"
        assert openai_tool["function"]["description"] == "Search the web"
        assert "parameters" in openai_tool["function"]
    
    def test_tool_fixes_array_schemas(self):
        """Test that array schemas without items are fixed for OpenAI compatibility."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketMCPTool
        
        mock_session = Mock()
        tool = WebSocketMCPTool(
            name="process",
            description="Process items",
            session=mock_session,
            input_schema={
                "type": "object",
                "properties": {
                    "items": {"type": "array"}  # Missing 'items' attribute
                }
            }
        )
        
        openai_tool = tool.to_openai_tool()
        items_schema = openai_tool["function"]["parameters"]["properties"]["items"]
        
        assert "items" in items_schema  # Should be added
        assert items_schema["items"]["type"] == "string"  # Default


class TestWebSocketTransport:
    """Test WebSocketTransport low-level implementation."""
    
    def test_transport_handles_session_id(self):
        """Test that transport handles MCP session ID."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketTransport
        
        transport = WebSocketTransport("ws://localhost:8080/mcp")
        
        assert transport.session_id is None
        
        transport.session_id = "test-session-123"
        assert transport.session_id == "test-session-123"
    
    def test_transport_initialization(self):
        """Test transport initializes with correct parameters."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketTransport
        
        transport = WebSocketTransport(
            "wss://example.com/mcp",
            auth_token="secret",
            max_retries=5,
            timeout=30.0
        )
        
        assert transport.url == "wss://example.com/mcp"
        assert transport.auth_token == "secret"
        assert transport.max_retries == 5
        assert transport.timeout == 30.0
    
    @pytest.mark.asyncio
    async def test_transport_send_requires_connection(self):
        """Test that send raises error when not connected."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketTransport
        
        transport = WebSocketTransport("ws://localhost:8080/mcp")
        
        with pytest.raises(RuntimeError, match="WebSocket not connected"):
            await transport.send({"test": 1})


class TestWebSocketReconnection:
    """Test WebSocket reconnection with exponential backoff."""
    
    def test_exponential_backoff_calculation(self):
        """Test exponential backoff delay calculation."""
        from praisonaiagents.mcp.mcp_websocket import calculate_backoff
        
        # First retry: base delay
        assert calculate_backoff(attempt=0, base_delay=1.0, max_delay=60.0) == 1.0
        
        # Second retry: 2x
        assert calculate_backoff(attempt=1, base_delay=1.0, max_delay=60.0) == 2.0
        
        # Third retry: 4x
        assert calculate_backoff(attempt=2, base_delay=1.0, max_delay=60.0) == 4.0
        
        # Should cap at max_delay
        assert calculate_backoff(attempt=10, base_delay=1.0, max_delay=60.0) == 60.0


class TestWebSocketMCPClient:
    """Test WebSocketMCPClient high-level interface."""
    
    def test_client_initialization(self):
        """Test client can be initialized with WebSocket URL."""
        # This test will be implemented after the basic structure is in place
        pass
    
    def test_client_lists_tools(self):
        """Test client can list available tools from server."""
        pass
    
    def test_client_calls_tool(self):
        """Test client can call a tool and get result."""
        pass
    
    def test_client_handles_timeout(self):
        """Test client handles timeout correctly."""
        pass
    
    def test_client_is_iterable(self):
        """Test client tools are iterable."""
        pass
    
    def test_client_converts_to_openai_tools(self):
        """Test client can convert all tools to OpenAI format."""
        pass


class TestMCPClassWebSocketIntegration:
    """Test MCP class integration with WebSocket transport."""
    
    def test_mcp_detects_ws_url(self):
        """Test MCP class detects ws:// URL and uses WebSocket transport."""
        # Will be implemented after WebSocketMCPClient is ready
        pass
    
    def test_mcp_detects_wss_url(self):
        """Test MCP class detects wss:// URL and uses WebSocket transport."""
        pass
    
    def test_mcp_websocket_tools_work_with_agent(self):
        """Test WebSocket tools work correctly with Agent class."""
        pass


class TestWebSocketKeepalive:
    """Test WebSocket keepalive/ping-pong handling."""
    
    def test_ping_interval_configurable(self):
        """Test that ping interval is configurable."""
        from praisonaiagents.mcp.mcp_websocket import WebSocketTransport
        
        transport = WebSocketTransport(
            "ws://localhost:8080/mcp",
            ping_interval=60.0,
            ping_timeout=20.0
        )
        
        assert transport.ping_interval == 60.0
        assert transport.ping_timeout == 20.0


class TestWebSocketPerformance:
    """Test WebSocket transport performance characteristics."""
    
    def test_lazy_import_websocket_module(self):
        """Test that mcp_websocket module can be imported."""
        # Just verify the module imports without errors
        from praisonaiagents.mcp.mcp_websocket import (
            is_websocket_url,
            calculate_backoff,
            WebSocketTransport,
            WebSocketMCPTool
        )
        
        # Verify functions exist
        assert callable(is_websocket_url)
        assert callable(calculate_backoff)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
