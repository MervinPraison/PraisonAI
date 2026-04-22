"""
Unit tests for bind-aware authentication posture.

Tests the core protocols and auth enforcement logic.
"""

import os
import pytest
from unittest.mock import patch

from praisonaiagents.gateway.protocols import AuthMode, is_loopback, resolve_auth_mode
from praisonaiagents.gateway.config import GatewayConfig
from praisonai.gateway.auth import assert_external_bind_safe, GatewayStartupError


class TestLoopbackDetection:
    """Test loopback interface detection."""
    
    def test_loopback_ipv4(self):
        """Test IPv4 loopback detection."""
        assert is_loopback("127.0.0.1") is True
        assert is_loopback("127.0.0.2") is True
        assert is_loopback("127.255.255.255") is True
    
    def test_loopback_ipv6(self):
        """Test IPv6 loopback detection."""
        assert is_loopback("::1") is True
        assert is_loopback("0:0:0:0:0:0:0:1") is True
    
    def test_localhost_hostname(self):
        """Test localhost hostname detection."""
        assert is_loopback("localhost") is True
    
    def test_non_loopback_addresses(self):
        """Test non-loopback addresses."""
        assert is_loopback("0.0.0.0") is False
        assert is_loopback("192.168.1.1") is False
        assert is_loopback("10.0.0.1") is False
        assert is_loopback("8.8.8.8") is False
        assert is_loopback("::") is False
        assert is_loopback("2001:db8::1") is False
    
    def test_invalid_addresses(self):
        """Test invalid IP addresses."""
        assert is_loopback("not-an-ip") is False
        assert is_loopback("999.999.999.999") is False
        assert is_loopback("") is False


class TestAuthModeResolution:
    """Test authentication mode resolution."""
    
    def test_loopback_default_to_local(self):
        """Test loopback interfaces default to local mode."""
        assert resolve_auth_mode("127.0.0.1") == "local"
        assert resolve_auth_mode("localhost") == "local"
        assert resolve_auth_mode("::1") == "local"
    
    def test_external_default_to_token(self):
        """Test external interfaces default to token mode."""
        assert resolve_auth_mode("0.0.0.0") == "token"
        assert resolve_auth_mode("192.168.1.1") == "token"
        assert resolve_auth_mode("8.8.8.8") == "token"
    
    def test_explicit_override(self):
        """Test explicit configuration overrides defaults."""
        assert resolve_auth_mode("127.0.0.1", "token") == "token"
        assert resolve_auth_mode("0.0.0.0", "local") == "local"
        assert resolve_auth_mode("127.0.0.1", "password") == "password"


class TestGatewayAuthEnforcement:
    """Test gateway auth enforcement logic."""
    
    def test_loopback_without_token_allows_start(self):
        """Test loopback bind without token allows start with warning."""
        config = GatewayConfig(bind_host="127.0.0.1", auth_token=None)
        
        # Should not raise exception
        assert_external_bind_safe(config)
    
    def test_loopback_with_token_allows_start(self):
        """Test loopback bind with token allows start."""
        config = GatewayConfig(bind_host="127.0.0.1", auth_token="test-token")
        
        # Should not raise exception
        assert_external_bind_safe(config)
    
    def test_external_without_token_blocks_start(self):
        """Test external bind without token blocks start."""
        config = GatewayConfig(bind_host="0.0.0.0", auth_token=None)
        
        with pytest.raises(GatewayStartupError) as exc_info:
            assert_external_bind_safe(config)
        
        assert "Cannot bind to 0.0.0.0 without an auth token" in str(exc_info.value)
        assert "praisonai onboard" in str(exc_info.value)
        assert "GATEWAY_AUTH_TOKEN" in str(exc_info.value)
    
    def test_external_with_token_allows_start(self):
        """Test external bind with token allows start."""
        config = GatewayConfig(bind_host="0.0.0.0", auth_token="secure-token")
        
        # Should not raise exception
        assert_external_bind_safe(config)
    
    def test_various_external_interfaces(self):
        """Test various external interface patterns."""
        external_hosts = ["0.0.0.0", "192.168.1.100", "10.0.0.1", "8.8.8.8"]
        
        for host in external_hosts:
            # Without token - should fail
            config = GatewayConfig(bind_host=host, auth_token=None)
            with pytest.raises(GatewayStartupError):
                assert_external_bind_safe(config)
            
            # With token - should pass
            config = GatewayConfig(bind_host=host, auth_token="token")
            assert_external_bind_safe(config)


class TestAuthTokenFingerprinting:
    """Test auth token fingerprinting for safe logging."""
    
    def test_token_fingerprint(self):
        """Test token fingerprinting."""
        from praisonai.gateway.auth import get_auth_token_fingerprint
        
        assert get_auth_token_fingerprint("") == "gw_****<none>"
        assert get_auth_token_fingerprint("abc") == "gw_****<short>"
        assert get_auth_token_fingerprint("abcd1234") == "gw_****1234"
        assert get_auth_token_fingerprint("very-long-token-12345") == "gw_****2345"


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""
    
    def test_development_scenario(self):
        """Test typical development scenario (loopback, no token)."""
        config = GatewayConfig(bind_host="127.0.0.1", auth_token=None)
        auth_mode = resolve_auth_mode(config.bind_host)
        
        assert auth_mode == "local"
        # Should allow start (permissive mode)
        assert_external_bind_safe(config)
    
    def test_production_lan_scenario(self):
        """Test production LAN scenario (external bind, requires token)."""
        config = GatewayConfig(bind_host="192.168.1.100", auth_token=None)
        auth_mode = resolve_auth_mode(config.bind_host)
        
        assert auth_mode == "token" 
        # Should block start without token
        with pytest.raises(GatewayStartupError):
            assert_external_bind_safe(config)
    
    def test_production_vps_scenario(self):
        """Test production VPS scenario (public bind, requires token).""" 
        config = GatewayConfig(bind_host="0.0.0.0", auth_token="secure-production-token")
        auth_mode = resolve_auth_mode(config.bind_host)
        
        assert auth_mode == "token"
        # Should allow start with token
        assert_external_bind_safe(config)