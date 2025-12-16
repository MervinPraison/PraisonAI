"""Tests for MCP Security Features - TDD approach.

These tests define the expected behavior of security features
per MCP Protocol Revision 2025-11-25.

Security features:
- Origin header validation (DNS rebinding prevention)
- Localhost binding recommendation
- Authentication header support
- Secure session ID handling
"""

import pytest


class TestOriginValidation:
    """Test Origin header validation for DNS rebinding prevention."""
    
    def test_valid_localhost_origins(self):
        """Test that localhost origins are accepted."""
        from praisonaiagents.mcp.mcp_security import is_valid_origin
        
        assert is_valid_origin("http://localhost:8080", allowed_origins=["localhost"]) is True
        assert is_valid_origin("http://127.0.0.1:3000", allowed_origins=["127.0.0.1"]) is True
        assert is_valid_origin("http://localhost", allowed_origins=["localhost"]) is True
    
    def test_valid_custom_origins(self):
        """Test that configured custom origins are accepted."""
        from praisonaiagents.mcp.mcp_security import is_valid_origin
        
        allowed = ["example.com", "api.example.com"]
        
        assert is_valid_origin("https://example.com", allowed_origins=allowed) is True
        assert is_valid_origin("https://api.example.com/path", allowed_origins=allowed) is True
    
    def test_invalid_origins_rejected(self):
        """Test that invalid origins are rejected."""
        from praisonaiagents.mcp.mcp_security import is_valid_origin
        
        allowed = ["localhost", "example.com"]
        
        assert is_valid_origin("https://evil.com", allowed_origins=allowed) is False
        assert is_valid_origin("https://example.com.evil.com", allowed_origins=allowed) is False
    
    def test_missing_origin_handling(self):
        """Test handling of missing Origin header."""
        from praisonaiagents.mcp.mcp_security import is_valid_origin
        
        # Missing origin should be rejected by default
        assert is_valid_origin(None, allowed_origins=["localhost"]) is False
        assert is_valid_origin("", allowed_origins=["localhost"]) is False
    
    def test_allow_missing_origin_option(self):
        """Test option to allow missing Origin header."""
        from praisonaiagents.mcp.mcp_security import is_valid_origin
        
        # Can optionally allow missing origin for non-browser clients
        assert is_valid_origin(None, allowed_origins=["localhost"], allow_missing=True) is True


class TestLocalhostBinding:
    """Test localhost binding recommendations."""
    
    def test_is_localhost_address(self):
        """Test detection of localhost addresses."""
        from praisonaiagents.mcp.mcp_security import is_localhost_address
        
        assert is_localhost_address("127.0.0.1") is True
        assert is_localhost_address("localhost") is True
        assert is_localhost_address("::1") is True  # IPv6 localhost
        assert is_localhost_address("0.0.0.0") is False  # All interfaces
        assert is_localhost_address("192.168.1.1") is False
    
    def test_should_bind_localhost_only(self):
        """Test recommendation for localhost-only binding."""
        from praisonaiagents.mcp.mcp_security import should_bind_localhost_only
        
        # Local servers should bind to localhost only
        assert should_bind_localhost_only(is_local=True) is True
        
        # Remote/production servers may bind to all interfaces
        assert should_bind_localhost_only(is_local=False) is False


class TestAuthenticationHeaders:
    """Test authentication header support."""
    
    def test_create_bearer_auth_header(self):
        """Test creating Bearer authentication header."""
        from praisonaiagents.mcp.mcp_security import create_auth_header
        
        header = create_auth_header("my-secret-token", auth_type="bearer")
        
        assert header == {"Authorization": "Bearer my-secret-token"}
    
    def test_create_basic_auth_header(self):
        """Test creating Basic authentication header."""
        from praisonaiagents.mcp.mcp_security import create_auth_header
        import base64
        
        header = create_auth_header("user:pass", auth_type="basic")
        
        expected = base64.b64encode(b"user:pass").decode()
        assert header == {"Authorization": f"Basic {expected}"}
    
    def test_create_custom_auth_header(self):
        """Test creating custom authentication header."""
        from praisonaiagents.mcp.mcp_security import create_auth_header
        
        header = create_auth_header("custom-value", auth_type="custom", header_name="X-API-Key")
        
        assert header == {"X-API-Key": "custom-value"}
    
    def test_validate_auth_header(self):
        """Test validating authentication header presence."""
        from praisonaiagents.mcp.mcp_security import validate_auth_header
        
        headers_with_auth = {"Authorization": "Bearer token"}
        headers_without_auth = {"Content-Type": "application/json"}
        
        assert validate_auth_header(headers_with_auth) is True
        assert validate_auth_header(headers_without_auth) is False


class TestSecureSessionHandling:
    """Test secure session ID handling."""
    
    def test_generate_secure_session_id(self):
        """Test generating cryptographically secure session ID."""
        from praisonaiagents.mcp.mcp_security import generate_secure_session_id
        
        session_id = generate_secure_session_id()
        
        # Should be non-empty
        assert len(session_id) > 0
        
        # Should be unique
        session_id2 = generate_secure_session_id()
        assert session_id != session_id2
        
        # Should contain only valid characters (visible ASCII)
        for char in session_id:
            assert 0x21 <= ord(char) <= 0x7E
    
    def test_session_id_length(self):
        """Test session ID has sufficient length for security."""
        from praisonaiagents.mcp.mcp_security import generate_secure_session_id
        
        session_id = generate_secure_session_id()
        
        # Should be at least 32 characters for security
        assert len(session_id) >= 32
    
    def test_session_id_entropy(self):
        """Test session ID has sufficient entropy."""
        from praisonaiagents.mcp.mcp_security import generate_secure_session_id
        
        # Generate multiple IDs and check they're all different
        ids = [generate_secure_session_id() for _ in range(100)]
        unique_ids = set(ids)
        
        assert len(unique_ids) == 100  # All should be unique


class TestDNSRebindingPrevention:
    """Test DNS rebinding attack prevention."""
    
    def test_extract_origin_host(self):
        """Test extracting host from Origin header."""
        from praisonaiagents.mcp.mcp_security import extract_origin_host
        
        assert extract_origin_host("http://localhost:8080") == "localhost"
        assert extract_origin_host("https://example.com:443/path") == "example.com"
        assert extract_origin_host("http://127.0.0.1") == "127.0.0.1"
    
    def test_detect_dns_rebinding_attempt(self):
        """Test detection of potential DNS rebinding attempts."""
        from praisonaiagents.mcp.mcp_security import is_potential_dns_rebinding
        
        # External origin trying to access localhost server
        assert is_potential_dns_rebinding(
            origin="https://evil.com",
            server_host="localhost"
        ) is True
        
        # Same origin is safe
        assert is_potential_dns_rebinding(
            origin="http://localhost:8080",
            server_host="localhost"
        ) is False


class TestSecurityConfig:
    """Test security configuration."""
    
    def test_security_config_defaults(self):
        """Test default security configuration."""
        from praisonaiagents.mcp.mcp_security import SecurityConfig
        
        config = SecurityConfig()
        
        # Secure defaults
        assert config.validate_origin is True
        assert config.allow_missing_origin is False
        assert "localhost" in config.allowed_origins
        assert "127.0.0.1" in config.allowed_origins
    
    def test_security_config_custom(self):
        """Test custom security configuration."""
        from praisonaiagents.mcp.mcp_security import SecurityConfig
        
        config = SecurityConfig(
            allowed_origins=["example.com"],
            allow_missing_origin=True,
            require_auth=True
        )
        
        assert "example.com" in config.allowed_origins
        assert config.allow_missing_origin is True
        assert config.require_auth is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
