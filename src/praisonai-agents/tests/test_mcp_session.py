"""Tests for MCP Session Management - TDD approach.

These tests define the expected behavior of session management for
Streamable HTTP transport per MCP Protocol Revision 2025-11-25.

Session management features:
- MCP-Session-Id header handling
- Session persistence across requests
- Session expiration handling (HTTP 404)
- Session termination via HTTP DELETE
- Session ID validation (visible ASCII 0x21-0x7E)
"""

import pytest


class TestSessionIdValidation:
    """Test session ID validation per MCP spec."""
    
    def test_valid_session_id_ascii(self):
        """Test that valid ASCII session IDs are accepted."""
        from praisonaiagents.mcp.mcp_session import is_valid_session_id
        
        # Valid session IDs (visible ASCII 0x21-0x7E)
        assert is_valid_session_id("abc123") is True
        assert is_valid_session_id("session-id-12345") is True
        assert is_valid_session_id("a1b2c3d4e5f6") is True
        assert is_valid_session_id("!@#$%^&*()") is True  # Special chars in range
        assert is_valid_session_id("UUID-1234-5678-90ab") is True
    
    def test_invalid_session_id_with_spaces(self):
        """Test that session IDs with spaces are rejected."""
        from praisonaiagents.mcp.mcp_session import is_valid_session_id
        
        assert is_valid_session_id("session id") is False
        assert is_valid_session_id(" leading") is False
        assert is_valid_session_id("trailing ") is False
    
    def test_invalid_session_id_with_control_chars(self):
        """Test that session IDs with control characters are rejected."""
        from praisonaiagents.mcp.mcp_session import is_valid_session_id
        
        assert is_valid_session_id("session\x00id") is False  # NULL
        assert is_valid_session_id("session\nid") is False    # Newline
        assert is_valid_session_id("session\tid") is False    # Tab
    
    def test_invalid_session_id_empty(self):
        """Test that empty session IDs are rejected."""
        from praisonaiagents.mcp.mcp_session import is_valid_session_id
        
        assert is_valid_session_id("") is False
        assert is_valid_session_id(None) is False
    
    def test_invalid_session_id_non_ascii(self):
        """Test that non-ASCII characters are rejected."""
        from praisonaiagents.mcp.mcp_session import is_valid_session_id
        
        assert is_valid_session_id("session\x7fid") is False  # DEL char
        assert is_valid_session_id("session\x80id") is False  # Extended ASCII


class TestSessionManager:
    """Test SessionManager class for managing MCP sessions."""
    
    def test_session_manager_creation(self):
        """Test SessionManager can be created."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        assert manager.session_id is None
        assert manager.is_active is False
    
    def test_session_manager_set_session_id(self):
        """Test setting session ID."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        manager.set_session_id("test-session-123")
        
        assert manager.session_id == "test-session-123"
        assert manager.is_active is True
    
    def test_session_manager_rejects_invalid_id(self):
        """Test that invalid session IDs are rejected."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        
        with pytest.raises(ValueError, match="Invalid session ID"):
            manager.set_session_id("invalid session")  # Contains space
    
    def test_session_manager_clear_session(self):
        """Test clearing session."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        manager.set_session_id("test-session-123")
        manager.clear()
        
        assert manager.session_id is None
        assert manager.is_active is False
    
    def test_session_manager_get_headers(self):
        """Test getting headers with session ID."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        
        # No session - no header
        headers = manager.get_headers()
        assert 'Mcp-Session-Id' not in headers
        
        # With session - include header
        manager.set_session_id("test-session-123")
        headers = manager.get_headers()
        assert headers['Mcp-Session-Id'] == "test-session-123"


class TestSessionFromResponse:
    """Test extracting session ID from HTTP response headers."""
    
    def test_extract_session_id_from_headers(self):
        """Test extracting session ID from response headers."""
        from praisonaiagents.mcp.mcp_session import extract_session_id
        
        headers = {'Mcp-Session-Id': 'new-session-456'}
        session_id = extract_session_id(headers)
        
        assert session_id == 'new-session-456'
    
    def test_extract_session_id_case_insensitive(self):
        """Test that header name is case-insensitive."""
        from praisonaiagents.mcp.mcp_session import extract_session_id
        
        # Various case combinations
        assert extract_session_id({'mcp-session-id': 'test'}) == 'test'
        assert extract_session_id({'MCP-SESSION-ID': 'test'}) == 'test'
        assert extract_session_id({'Mcp-Session-Id': 'test'}) == 'test'
    
    def test_extract_session_id_missing(self):
        """Test when session ID header is missing."""
        from praisonaiagents.mcp.mcp_session import extract_session_id
        
        headers = {'Content-Type': 'application/json'}
        session_id = extract_session_id(headers)
        
        assert session_id is None


class TestSessionExpiration:
    """Test handling of session expiration (HTTP 404)."""
    
    def test_is_session_expired_404(self):
        """Test that HTTP 404 indicates session expiration."""
        from praisonaiagents.mcp.mcp_session import is_session_expired
        
        assert is_session_expired(404) is True
        assert is_session_expired(200) is False
        assert is_session_expired(400) is False
        assert is_session_expired(500) is False
    
    def test_session_manager_marks_expired(self):
        """Test that session manager can mark session as expired."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        manager.set_session_id("test-session")
        
        manager.mark_expired()
        
        assert manager.is_expired is True
        assert manager.is_active is False


class TestProtocolVersion:
    """Test MCP-Protocol-Version header handling."""
    
    def test_default_protocol_version(self):
        """Test default protocol version is 2025-03-26 for compatibility."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        headers = manager.get_headers()
        
        # Default version for backward compatibility
        assert headers.get('Mcp-Protocol-Version') == '2025-03-26'
    
    def test_set_protocol_version(self):
        """Test setting negotiated protocol version."""
        from praisonaiagents.mcp.mcp_session import SessionManager
        
        manager = SessionManager()
        manager.set_protocol_version('2025-11-25')
        
        headers = manager.get_headers()
        assert headers['Mcp-Protocol-Version'] == '2025-11-25'
    
    def test_valid_protocol_versions(self):
        """Test that valid protocol versions are accepted."""
        from praisonaiagents.mcp.mcp_session import is_valid_protocol_version
        
        assert is_valid_protocol_version('2025-03-26') is True
        assert is_valid_protocol_version('2025-06-18') is True
        assert is_valid_protocol_version('2025-11-25') is True
        assert is_valid_protocol_version('2024-11-05') is True
    
    def test_invalid_protocol_versions(self):
        """Test that invalid protocol versions are rejected."""
        from praisonaiagents.mcp.mcp_session import is_valid_protocol_version
        
        assert is_valid_protocol_version('invalid') is False
        assert is_valid_protocol_version('2025') is False
        assert is_valid_protocol_version('') is False


class TestHTTPStreamSessionIntegration:
    """Test session management integration with HTTPStreamTransport."""
    
    def test_transport_uses_session_manager(self):
        """Test that HTTPStreamTransport uses SessionManager."""
        # This will be implemented when we update HTTPStreamTransport
        pass
    
    def test_transport_handles_session_from_init_response(self):
        """Test that transport extracts session ID from InitializeResult."""
        pass
    
    def test_transport_includes_session_in_requests(self):
        """Test that transport includes session ID in subsequent requests."""
        pass
    
    def test_transport_handles_session_expiration(self):
        """Test that transport handles HTTP 404 session expiration."""
        pass
    
    def test_transport_can_terminate_session(self):
        """Test that transport can terminate session via HTTP DELETE."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
