"""
Unit tests for bind-aware authentication posture.

Tests the core protocols and auth enforcement logic.
"""

import os
import pytest
from unittest.mock import patch

from praisonaiagents.gateway.protocols import AuthMode, is_loopback, resolve_auth_mode
from praisonaiagents.gateway.config import GatewayConfig
from praisonai_bot.gateway.auth import assert_external_bind_safe, GatewayStartupError


class TestGatewayAuthTokenEnvSync:
    """Test gateway auth token env synchronization."""

    def test_config_token_overrides_stale_env_token(self, monkeypatch):
        """Gateway should export configured token for all auth paths."""
        from praisonai_bot.gateway.server import WebSocketGateway

        monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "stale-token")
        config = GatewayConfig(bind_host="127.0.0.1", auth_token="fresh-token")

        gateway = WebSocketGateway(config=config)

        assert gateway.config.auth_token == "fresh-token"
        assert os.environ["GATEWAY_AUTH_TOKEN"] == "fresh-token"


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
            
            # With a strong token - should pass
            config = GatewayConfig(bind_host=host, auth_token="f3a9c1b27d0e4a56")
            assert_external_bind_safe(config)


class TestWeakSecretGuard:
    """Test known-weak/placeholder secret rejection (Issue #3259)."""

    def test_is_weak_secret_detects_placeholders(self):
        from praisonaiagents.gateway.protocols import is_weak_secret

        for weak in (
            "change-me", "CHANGE-ME", " changeme ", "your-token-here",
            "secret", "password", "test", "token", "admin",
            "$(openssl rand -hex 16)", "$(openssl rand -hex 32)",
        ):
            assert is_weak_secret(weak) is True, weak

    def test_is_weak_secret_allows_strong(self):
        from praisonaiagents.gateway.protocols import is_weak_secret

        assert is_weak_secret("f3a9c1b27d0e4a56d8e1") is False
        assert is_weak_secret("secure-production-token-xyz") is False

    def test_is_weak_secret_treats_empty_as_weak(self):
        from praisonaiagents.gateway.protocols import is_weak_secret

        assert is_weak_secret("") is True
        assert is_weak_secret(None) is True

    def test_assert_gateway_secret_strong_raises_on_weak(self):
        from praisonaiagents.gateway.protocols import (
            assert_gateway_secret_strong,
            WeakGatewaySecretError,
        )

        with pytest.raises(WeakGatewaySecretError) as exc_info:
            assert_gateway_secret_strong("change-me", field="gateway.auth_token")
        assert exc_info.value.field == "gateway.auth_token"

    def test_assert_gateway_secret_strong_passes_strong(self):
        from praisonaiagents.gateway.protocols import assert_gateway_secret_strong

        # Should not raise
        assert_gateway_secret_strong("f3a9c1b27d0e4a56", field="gateway.auth_token")

    def test_external_bind_rejects_weak_token(self):
        """External bind with a placeholder token must fail closed."""
        config = GatewayConfig(bind_host="0.0.0.0", auth_token="change-me")

        with pytest.raises(GatewayStartupError) as exc_info:
            assert_external_bind_safe(config)

        assert "known-weak" in str(exc_info.value)
        assert "gateway.auth_token" in str(exc_info.value)

    def test_external_bind_rejects_literal_openssl_hint(self):
        """The copy-paste footgun literal must be rejected on external bind."""
        config = GatewayConfig(
            bind_host="192.168.1.10", auth_token="$(openssl rand -hex 16)"
        )
        with pytest.raises(GatewayStartupError):
            assert_external_bind_safe(config)

    def test_external_bind_accepts_strong_token(self):
        config = GatewayConfig(bind_host="0.0.0.0", auth_token="f3a9c1b27d0e4a56")
        assert_external_bind_safe(config)

    def test_loopback_bind_warns_but_allows_weak_token(self):
        """Loopback bind downgrades weak-secret to a warning (permissive)."""
        config = GatewayConfig(bind_host="127.0.0.1", auth_token="change-me")
        # Should not raise
        assert_external_bind_safe(config)


class TestLoopbackAuthBypassDefault:
    """Test loopback auth bypass is permissive-by-default on loopback binds (#2945)."""

    def _bypass(self, bind_host, client_host, headers=None, allow_env=None):
        from praisonai_bot.gateway.server import _should_bypass_loopback_auth

        return _should_bypass_loopback_auth(
            bind_host, client_host, headers or {}, allow_env=allow_env
        )

    def test_loopback_bind_permissive_by_default(self):
        """Fresh loopback bind allows local requests without an explicit env flag."""
        assert self._bypass("127.0.0.1", "127.0.0.1", allow_env="") is True
        assert self._bypass("localhost", "127.0.0.1", allow_env="") is True
        assert self._bypass("::1", "::1", allow_env="") is True

    def test_external_bind_strict_by_default(self):
        """External binds stay strict — no bypass even from a localhost client."""
        assert self._bypass("0.0.0.0", "127.0.0.1", allow_env="") is False
        assert self._bypass("192.168.1.10", "127.0.0.1", allow_env="") is False

    def test_explicit_true_forces_bypass_on_external_bind(self):
        """ALLOW_LOOPBACK_BYPASS=true keeps legacy force-enable behaviour."""
        assert self._bypass("0.0.0.0", "127.0.0.1", allow_env="true") is True
        assert self._bypass("0.0.0.0", "127.0.0.1", allow_env="1") is True

    def test_explicit_false_disables_bypass_on_loopback_bind(self):
        """ALLOW_LOOPBACK_BYPASS=false opts back into strict auth on loopback."""
        assert self._bypass("127.0.0.1", "127.0.0.1", allow_env="false") is False
        assert self._bypass("127.0.0.1", "127.0.0.1", allow_env="0") is False

    def test_non_local_client_never_bypasses(self):
        """A remote client on a loopback-bound gateway still requires auth."""
        assert self._bypass("127.0.0.1", "192.168.1.5", allow_env="") is False

    def test_proxy_headers_block_bypass(self):
        """Requests carrying proxy headers can't inherit loopback trust."""
        for header in ("x-forwarded-for", "via", "x-real-ip", "x-forwarded-host"):
            assert (
                self._bypass("127.0.0.1", "127.0.0.1", {header: "1.2.3.4"}, allow_env="")
                is False
            )

    def test_missing_client_host_blocks_bypass(self):
        assert self._bypass("127.0.0.1", None, allow_env="") is False

    def test_semantic_loopback_client_bypasses(self):
        """Loopback clients reported as non-canonical addresses still bypass.

        L4-forwarded/local peers can appear as ``127.0.0.2``,
        ``127.255.255.255`` or the expanded IPv6 form ``0:0:0:0:0:0:0:1``.
        These are semantically loopback and must not get a spurious 401.
        """
        for client in ("127.0.0.2", "127.255.255.255", "0:0:0:0:0:0:0:1"):
            assert self._bypass("127.0.0.1", client, allow_env="") is True

    def test_non_loopback_client_string_blocks_bypass(self):
        """A non-loopback client address must not bypass on a loopback bind."""
        assert self._bypass("127.0.0.1", "10.0.0.5", allow_env="") is False
        assert self._bypass("127.0.0.1", "2001:db8::1", allow_env="") is False

    def test_env_var_default_read(self, monkeypatch):
        """When allow_env is not passed, the env var drives the decision."""
        from praisonai_bot.gateway.server import _should_bypass_loopback_auth

        monkeypatch.delenv("ALLOW_LOOPBACK_BYPASS", raising=False)
        assert _should_bypass_loopback_auth("127.0.0.1", "127.0.0.1", {}) is True
        assert _should_bypass_loopback_auth("0.0.0.0", "127.0.0.1", {}) is False

        monkeypatch.setenv("ALLOW_LOOPBACK_BYPASS", "false")
        assert _should_bypass_loopback_auth("127.0.0.1", "127.0.0.1", {}) is False


class TestAuthTokenFingerprinting:
    """Test auth token fingerprinting for safe logging."""
    
    def test_token_fingerprint(self):
        """Test token fingerprinting."""
        from praisonai_bot.gateway.auth import get_auth_token_fingerprint
        
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