"""Tests for MCP Backward Compatibility - TDD approach.

These tests ensure backward compatibility with older MCP servers
and the deprecated HTTP+SSE transport from protocol version 2024-11-05.

Backward compatibility features:
- Legacy SSE endpoint support (/sse suffix)
- Fallback detection for older servers
- Automatic transport negotiation
"""

import pytest


class TestLegacySSESupport:
    """Test legacy SSE transport support."""
    
    def test_sse_url_detection(self):
        """Test that /sse URLs are detected as legacy SSE."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("http://localhost:8080/sse") == "sse"
        assert get_transport_type("https://example.com/api/sse") == "sse"
    
    def test_non_sse_http_uses_streamable(self):
        """Test that non-/sse HTTP URLs use Streamable HTTP."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("http://localhost:8080/mcp") == "http_stream"
        assert get_transport_type("https://example.com/api") == "http_stream"


class TestTransportNegotiation:
    """Test automatic transport negotiation."""
    
    def test_detect_streamable_http_support(self):
        """Test detection of Streamable HTTP support."""
        from praisonaiagents.mcp.mcp_compat import detect_transport_support
        
        # Successful POST to MCP endpoint indicates Streamable HTTP
        result = detect_transport_support(
            response_status=200,
            content_type="application/json"
        )
        assert result == "http_stream"
    
    def test_detect_legacy_sse_fallback(self):
        """Test fallback to legacy SSE on specific error codes."""
        from praisonaiagents.mcp.mcp_compat import detect_transport_support
        
        # 400, 404, 405 indicate need for legacy SSE
        assert detect_transport_support(response_status=400) == "sse"
        assert detect_transport_support(response_status=404) == "sse"
        assert detect_transport_support(response_status=405) == "sse"
    
    def test_detect_sse_from_event_stream(self):
        """Test detection of SSE from content type."""
        from praisonaiagents.mcp.mcp_compat import detect_transport_support
        
        result = detect_transport_support(
            response_status=200,
            content_type="text/event-stream"
        )
        # SSE response indicates legacy transport
        assert result in ["sse", "http_stream"]


class TestProtocolVersionCompatibility:
    """Test protocol version compatibility."""
    
    def test_supports_2024_11_05(self):
        """Test support for protocol version 2024-11-05."""
        from praisonaiagents.mcp.mcp_session import is_valid_protocol_version
        
        assert is_valid_protocol_version("2024-11-05") is True
    
    def test_supports_2025_03_26(self):
        """Test support for protocol version 2025-03-26."""
        from praisonaiagents.mcp.mcp_session import is_valid_protocol_version
        
        assert is_valid_protocol_version("2025-03-26") is True
    
    def test_supports_2025_11_25(self):
        """Test support for protocol version 2025-11-25."""
        from praisonaiagents.mcp.mcp_session import is_valid_protocol_version
        
        assert is_valid_protocol_version("2025-11-25") is True


class TestMCPClassBackwardCompat:
    """Test MCP class backward compatibility."""
    
    def test_mcp_accepts_sse_url(self):
        """Test MCP class accepts /sse URLs."""
        # This is a design test - actual connection would require server
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        # Verify URL would be routed to SSE transport
        assert get_transport_type("http://localhost:8080/sse") == "sse"
    
    def test_mcp_accepts_command_string(self):
        """Test MCP class accepts command strings (stdio)."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("python server.py") == "stdio"
        assert get_transport_type("npx @mcp/server") == "stdio"
    
    def test_mcp_accepts_http_url(self):
        """Test MCP class accepts HTTP URLs."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("http://localhost:8080/mcp") == "http_stream"
    
    def test_mcp_accepts_websocket_url(self):
        """Test MCP class accepts WebSocket URLs."""
        from praisonaiagents.mcp.mcp_transport import get_transport_type
        
        assert get_transport_type("ws://localhost:8080/mcp") == "websocket"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
