"""
Unit tests for zero-config MCP OAuth discovery, registration, and provider.

These cover the pure/parsing logic and the storage-driven provider paths that
do not require live network access or a browser.
"""
import pytest


class TestParseWWWAuthenticate:
    def test_none_returns_empty(self):
        from praisonaiagents.mcp.oauth_discovery import parse_www_authenticate
        assert parse_www_authenticate(None) == {}

    def test_parses_resource_metadata(self):
        from praisonaiagents.mcp.oauth_discovery import parse_www_authenticate
        header = 'Bearer resource_metadata="https://api.example.com/.well-known/oauth-protected-resource", error="invalid_token"'
        params = parse_www_authenticate(header)
        assert params["resource_metadata"] == "https://api.example.com/.well-known/oauth-protected-resource"
        assert params["error"] == "invalid_token"

    def test_non_bearer_still_parses_params(self):
        from praisonaiagents.mcp.oauth_discovery import parse_www_authenticate
        params = parse_www_authenticate('scope="read write"')
        assert params["scope"] == "read write"


class TestHttpsGuard:
    def test_rejects_plain_http_remote(self):
        from praisonaiagents.mcp.oauth_discovery import _require_https
        with pytest.raises(ValueError):
            _require_https("http://evil.example.com/.well-known/x")

    def test_allows_https(self):
        from praisonaiagents.mcp.oauth_discovery import _require_https
        _require_https("https://api.example.com/.well-known/x")

    def test_allows_loopback_http(self):
        from praisonaiagents.mcp.oauth_discovery import _require_https
        _require_https("http://127.0.0.1:8080/.well-known/x")


class TestWellKnownCandidates:
    def test_builds_origin_candidates(self):
        from praisonaiagents.mcp.oauth_discovery import _wellknown_candidates
        candidates = _wellknown_candidates("https://api.example.com/mcp/v1")
        assert "https://api.example.com/.well-known/oauth-protected-resource" in candidates
        assert "https://api.example.com/.well-known/oauth-authorization-server" in candidates
        assert "https://api.example.com/.well-known/openid-configuration" in candidates


class TestEndpointHttpsValidation:
    def test_rejects_plaintext_advertised_endpoints(self, monkeypatch):
        from praisonaiagents.mcp import oauth_discovery

        monkeypatch.setattr(
            oauth_discovery, "discover_protected_resource",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            oauth_discovery, "discover_authorization_server",
            lambda *a, **k: {
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "http://auth.example.com/token",
            },
        )
        with pytest.raises(ValueError):
            oauth_discovery.discover_oauth_metadata("https://api.example.com/mcp")

    def test_accepts_all_https_endpoints(self, monkeypatch):
        from praisonaiagents.mcp import oauth_discovery

        monkeypatch.setattr(
            oauth_discovery, "discover_protected_resource",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            oauth_discovery, "discover_authorization_server",
            lambda *a, **k: {
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "registration_endpoint": "https://auth.example.com/register",
            },
        )
        meta = oauth_discovery.discover_oauth_metadata("https://api.example.com/mcp")
        assert meta["token_endpoint"] == "https://auth.example.com/token"


class TestRedirectRevalidation:
    def test_rejects_redirect_to_plaintext(self, monkeypatch):
        from praisonaiagents.mcp import oauth_discovery

        class _Hop:
            url = "http://internal.local/.well-known/x"

        class _Resp:
            url = "http://internal.local/.well-known/x"
            history = [_Hop()]

            def raise_for_status(self):
                pass

            def json(self):
                return {}

        class _Requests:
            @staticmethod
            def get(*a, **k):
                return _Resp()

        monkeypatch.setitem(
            __import__("sys").modules, "requests", _Requests()
        )
        with pytest.raises(ValueError):
            oauth_discovery._get_json("https://api.example.com/.well-known/x")


class TestRegistrationGuard:
    def test_rejects_insecure_registration(self):
        from praisonaiagents.mcp.oauth_registration import register_client
        with pytest.raises(ValueError):
            register_client(
                "http://evil.example.com/register",
                redirect_uris=["http://127.0.0.1:19876/mcp/oauth/callback"],
            )


class TestProviderTokenReuse:
    @pytest.fixture
    def storage(self, tmp_path):
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
        return MCPAuthStorage(filepath=str(tmp_path / "mcp-auth.json"))

    def test_returns_valid_stored_token(self, storage):
        import time
        from praisonaiagents.mcp.oauth_provider import MCPOAuthProvider

        url = "https://api.example.com/mcp"
        storage.set_tokens(
            "example",
            {"access_token": "tok123", "expires_at": time.time() + 3600},
            server_url=url,
        )
        provider = MCPOAuthProvider("example", url, storage=storage)
        assert provider.get_valid_token() == "tok123"
        assert provider.ensure_authenticated() == "tok123"

    def test_expired_token_without_refresh_returns_none(self, storage):
        import time
        from praisonaiagents.mcp.oauth_provider import MCPOAuthProvider

        url = "https://api.example.com/mcp"
        storage.set_tokens(
            "example",
            {"access_token": "old", "expires_at": time.time() - 10},
            server_url=url,
        )
        provider = MCPOAuthProvider("example", url, storage=storage)
        assert provider.get_valid_token() is None

    def test_headless_raises_interactive_required(self, storage, monkeypatch):
        from praisonaiagents.mcp import oauth_provider
        from praisonaiagents.mcp.oauth_provider import (
            MCPOAuthProvider,
            InteractiveAuthRequired,
        )

        url = "https://api.example.com/mcp"

        def fake_discover(server_url, www_authenticate=None, timeout=10.0):
            return {
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
                "registration_endpoint": "https://auth.example.com/register",
                "scopes_supported": ["read"],
                "resource": None,
            }

        def fake_register(endpoint, redirect_uris, scope=None, timeout=10.0):
            return {"client_id": "dyn-client-123"}

        monkeypatch.setattr(
            oauth_provider, "discover_oauth_metadata", fake_discover, raising=False
        )
        monkeypatch.setattr(
            "praisonaiagents.mcp.oauth_discovery.discover_oauth_metadata",
            fake_discover,
        )
        monkeypatch.setattr(
            "praisonaiagents.mcp.oauth_registration.register_client",
            fake_register,
        )

        provider = MCPOAuthProvider(
            "example", url, storage=storage, open_browser=False
        )
        with pytest.raises(InteractiveAuthRequired):
            provider.ensure_authenticated()

        entry = storage.get_for_url("example", url)
        assert entry["client_info"]["client_id"] == "dyn-client-123"


class TestLazyExports:
    def test_exports_available(self):
        import praisonaiagents.mcp as mcp
        assert mcp.discover_oauth_metadata is not None
        assert mcp.parse_www_authenticate is not None
        assert mcp.register_client is not None
        assert mcp.MCPOAuthProvider is not None
        assert mcp.InteractiveAuthRequired is not None
