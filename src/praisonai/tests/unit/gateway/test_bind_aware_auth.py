"""
Tests for bind-aware authentication posture in the gateway.

This module tests the core authentication logic that determines whether
authentication is required based on the bind interface (loopback vs external).
"""

import pytest
from unittest.mock import patch, MagicMock

from praisonaiagents.gateway.protocols import (
    AuthMode,
    is_loopback,
    resolve_auth_mode,
)
from praisonai.gateway.auth import (
    GatewayAuthEnforcer,
    GatewayStartupError,
    assert_external_bind_safe,
)


class TestIsLoopback:
    """Test the is_loopback function with various host inputs."""
    
    def test_ipv4_loopback_addresses(self):
        """Test IPv4 loopback addresses are correctly identified."""
        assert is_loopback("127.0.0.1") is True
        assert is_loopback("127.0.0.2") is True  # Any 127.x.x.x
        assert is_loopback("127.255.255.255") is True
    
    def test_ipv6_loopback_addresses(self):
        """Test IPv6 loopback addresses are correctly identified."""
        assert is_loopback("::1") is True
        assert is_loopback("0:0:0:0:0:0:0:1") is True
    
    def test_localhost_strings(self):
        """Test localhost string representations."""
        assert is_loopback("localhost") is True
        assert is_loopback("LOCALHOST") is True
        assert is_loopback("local") is True
    
    def test_external_ipv4_addresses(self):
        """Test external IPv4 addresses are not considered loopback."""
        assert is_loopback("0.0.0.0") is False
        assert is_loopback("192.168.1.1") is False
        assert is_loopback("10.0.0.1") is False
        assert is_loopback("8.8.8.8") is False
    
    def test_external_ipv6_addresses(self):
        """Test external IPv6 addresses are not considered loopback."""
        assert is_loopback("::") is False
        assert is_loopback("2001:db8::1") is False
    
    def test_invalid_inputs(self):
        """Test invalid or edge case inputs."""
        assert is_loopback("") is False
        assert is_loopback("invalid-host") is False
        assert is_loopback("not.a.valid.ip") is False


class TestResolveAuthMode:
    """Test the auth mode resolution logic."""
    
    def test_loopback_default_to_local_mode(self):
        """Test that loopback interfaces default to local mode."""
        assert resolve_auth_mode("127.0.0.1", None) == "local"
        assert resolve_auth_mode("localhost", None) == "local"
        assert resolve_auth_mode("::1", None) == "local"
    
    def test_external_default_to_token_mode(self):
        """Test that external interfaces default to token mode."""
        assert resolve_auth_mode("0.0.0.0", None) == "token"
        assert resolve_auth_mode("192.168.1.1", None) == "token"
        assert resolve_auth_mode("10.0.0.1", None) == "token"
    
    def test_explicit_config_overrides_default(self):
        """Test that explicit configuration overrides the default."""
        assert resolve_auth_mode("127.0.0.1", "token") == "token"
        assert resolve_auth_mode("0.0.0.0", "local") == "local"
        assert resolve_auth_mode("192.168.1.1", "password") == "password"


class TestGatewayAuthEnforcer:
    """Test the GatewayAuthEnforcer implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.enforcer = GatewayAuthEnforcer()
    
    def test_local_mode_on_loopback_is_valid(self):
        """Test that local mode on loopback passes validation."""
        # Should not raise
        self.enforcer.validate_auth_config(
            auth_mode="local",
            bind_host="127.0.0.1",
            auth_token=None
        )
    
    def test_local_mode_on_external_raises_error(self):
        """Test that local mode on external interface raises error."""
        with pytest.raises(GatewayStartupError) as excinfo:
            self.enforcer.validate_auth_config(
                auth_mode="local",
                bind_host="0.0.0.0",
                auth_token=None
            )
        
        assert "Cannot use local mode on external interface" in str(excinfo.value)
        assert "Set GATEWAY_AUTH_TOKEN" in str(excinfo.value)
    
    def test_token_mode_without_token_on_external_raises_error(self):
        """Test that token mode without token on external interface raises error."""
        with pytest.raises(GatewayStartupError) as excinfo:
            self.enforcer.validate_auth_config(
                auth_mode="token",
                bind_host="0.0.0.0",
                auth_token=None
            )
        
        assert "Cannot bind to 0.0.0.0 without an auth token" in str(excinfo.value)
        assert "praisonai onboard" in str(excinfo.value)
    
    def test_token_mode_with_token_on_external_is_valid(self):
        """Test that token mode with token on external interface is valid."""
        # Should not raise
        self.enforcer.validate_auth_config(
            auth_mode="token",
            bind_host="0.0.0.0",
            auth_token="test-token-123"
        )
    
    def test_check_request_auth_local_mode_always_passes(self):
        """Test that local mode always allows requests."""
        assert self.enforcer.check_request_auth(
            auth_mode="local",
            request_token=None,
            expected_token="secret"
        ) is True
        
        assert self.enforcer.check_request_auth(
            auth_mode="local",
            request_token="wrong",
            expected_token="secret"
        ) is True
    
    def test_check_request_auth_token_mode_requires_token(self):
        """Test that token mode requires correct token."""
        # No token provided
        assert self.enforcer.check_request_auth(
            auth_mode="token",
            request_token=None,
            expected_token="secret"
        ) is False
        
        # Wrong token
        assert self.enforcer.check_request_auth(
            auth_mode="token",
            request_token="wrong",
            expected_token="secret"
        ) is False
        
        # Correct token
        assert self.enforcer.check_request_auth(
            auth_mode="token",
            request_token="secret",
            expected_token="secret"
        ) is True
    
    def test_check_request_auth_no_expected_token_allows_all(self):
        """Test that token mode with no expected token allows all requests."""
        # This handles the case where validation failed to catch the issue
        assert self.enforcer.check_request_auth(
            auth_mode="token",
            request_token=None,
            expected_token=None
        ) is True


class TestAssertExternalBindSafe:
    """Test the main gateway startup validation function."""
    
    def test_loopback_config_passes_validation(self):
        """Test that loopback configuration passes validation."""
        config = MagicMock()
        config.host = "127.0.0.1"
        config.bind_host = "127.0.0.1"
        config.auth_token = None
        
        # Should not raise
        assert_external_bind_safe(config)
    
    def test_external_config_with_token_passes_validation(self):
        """Test that external configuration with token passes validation."""
        config = MagicMock()
        config.host = "0.0.0.0"
        config.bind_host = "0.0.0.0"
        config.auth_token = "test-token-123"
        
        # Should not raise
        assert_external_bind_safe(config)
    
    def test_external_config_without_token_raises_error(self):
        """Test that external configuration without token raises error."""
        config = MagicMock()
        config.host = "0.0.0.0"
        config.bind_host = "0.0.0.0"
        config.auth_token = None
        
        with pytest.raises(GatewayStartupError):
            assert_external_bind_safe(config)
    
    def test_fallback_to_host_when_bind_host_missing(self):
        """Test fallback to host when bind_host is not available."""
        config = MagicMock()
        config.host = "0.0.0.0"
        config.auth_token = "test-token"
        # No bind_host attribute
        del config.bind_host
        
        # Should not raise (has token)
        assert_external_bind_safe(config)
        
        # Should raise if no token
        config.auth_token = None
        with pytest.raises(GatewayStartupError):
            assert_external_bind_safe(config)


class TestIntegration:
    """Integration tests for the complete authentication flow."""
    
    def test_complete_auth_flow_loopback_permissive(self):
        """Test complete auth flow for loopback interface (permissive)."""
        bind_host = "127.0.0.1"
        auth_mode = resolve_auth_mode(bind_host, None)
        assert auth_mode == "local"
        
        enforcer = GatewayAuthEnforcer()
        
        # Validation should pass without token
        enforcer.validate_auth_config(
            auth_mode=auth_mode,
            bind_host=bind_host,
            auth_token=None
        )
        
        # Request auth should always pass
        assert enforcer.check_request_auth(
            auth_mode=auth_mode,
            request_token=None,
            expected_token=None
        ) is True
    
    def test_complete_auth_flow_external_strict(self):
        """Test complete auth flow for external interface (strict)."""
        bind_host = "0.0.0.0"
        auth_mode = resolve_auth_mode(bind_host, None)
        assert auth_mode == "token"
        
        enforcer = GatewayAuthEnforcer()
        
        # Validation should fail without token
        with pytest.raises(GatewayStartupError):
            enforcer.validate_auth_config(
                auth_mode=auth_mode,
                bind_host=bind_host,
                auth_token=None
            )
        
        # Validation should pass with token
        token = "test-secret-token"
        enforcer.validate_auth_config(
            auth_mode=auth_mode,
            bind_host=bind_host,
            auth_token=token
        )
        
        # Request auth should require correct token
        assert enforcer.check_request_auth(
            auth_mode=auth_mode,
            request_token=None,
            expected_token=token
        ) is False
        
        assert enforcer.check_request_auth(
            auth_mode=auth_mode,
            request_token="wrong",
            expected_token=token
        ) is False
        
        assert enforcer.check_request_auth(
            auth_mode=auth_mode,
            request_token=token,
            expected_token=token
        ) is True


if __name__ == "__main__":
    pytest.main([__file__])