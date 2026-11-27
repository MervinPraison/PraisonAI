"""Unit tests for OAuth bearer attachment and 401 handling in Streamable HTTP MCP."""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import patch

import httpx
import pytest


def _make_storage(tmp_path):
    from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage

    return MCPAuthStorage(filepath=str(tmp_path / "mcp-auth.json"))


class TestInteractiveAuthRequiredHierarchy:
    def test_subclasses_runtime_error_and_praisonai_error(self):
        from praisonaiagents.errors import PraisonAIError
        from praisonaiagents.mcp.oauth_provider import InteractiveAuthRequired

        err = InteractiveAuthRequired("Run `praisonai mcp auth github`")
        assert isinstance(err, RuntimeError)
        assert isinstance(err, PraisonAIError)
        assert str(err) == "Run `praisonai mcp auth github`"


class TestStorageFindByUrl:
    def test_find_by_url_matches_and_misses(self, tmp_path):
        storage = _make_storage(tmp_path)
        storage.set_tokens(
            "github",
            {"access_token": "tok-gh"},
            server_url="https://api.github.com/mcp",
        )
        found = storage.find_by_url("https://api.github.com/mcp")
        assert found is not None
        name, entry = found
        assert name == "github"
        assert entry["tokens"]["access_token"] == "tok-gh"
        assert storage.find_by_url("https://other.example/mcp") is None


class TestHTTPStreamOAuthFlow:
    def test_stored_bearer_attached_automatically(self, tmp_path):
        from praisonaiagents.mcp.mcp_http_stream import _build_httpx_oauth

        url = "https://mcp.example/mcp"
        storage = _make_storage(tmp_path)
        storage.set_tokens(
            "github",
            {"access_token": "stored-secret-token", "expires_at": time.time() + 3600},
            server_url=url,
        )

        auth = _build_httpx_oauth(url, options={"auth_storage": storage})
        assert auth is not None

        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((str(request.url), dict(request.headers)))
            return httpx.Response(200, json={"ok": True})

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), auth=auth
            ) as client:
                return await client.post(url, json={"jsonrpc": "2.0", "id": 1})

        resp = asyncio.run(run())
        assert resp.status_code == 200
        assert len(seen) == 1
        assert seen[0][0] == url
        assert seen[0][1]["authorization"] == "Bearer stored-secret-token"

    @pytest.mark.parametrize("hdr_name", ["Authorization", "authorization"])
    def test_explicit_authorization_header_not_overwritten(self, tmp_path, hdr_name):
        from praisonaiagents.mcp.mcp_http_stream import _build_httpx_oauth

        url = "https://mcp.example/mcp"
        storage = _make_storage(tmp_path)
        storage.set_tokens("github", {"access_token": "stored-tok"}, server_url=url)

        auth = _build_httpx_oauth(
            url,
            headers={hdr_name: "Bearer explicit-tok"},
            options={"oauth": True, "auth_storage": storage},
        )
        assert auth is None

    def test_401_triggers_refresh_and_retries_once_without_logging_tokens(
        self, tmp_path, monkeypatch, caplog
    ):
        from praisonaiagents.mcp import oauth_discovery
        from praisonaiagents.mcp.mcp_http_stream import _build_httpx_oauth

        url = "https://mcp.example/mcp"
        storage = _make_storage(tmp_path)
        storage.set_client_info("github", {"client_id": "cid-1"}, server_url=url)
        storage.set_tokens(
            "github",
            {
                "access_token": "old-secret-tok",
                "refresh_token": "ref-secret-tok",
                "token_endpoint": "https://auth.example/token",
                "expires_at": time.time() + 3600,  # revoked server-side before local expiry
            },
            server_url=url,
        )

        class _FakeTokenResp:
            status_code = 200

            def json(self):
                return {"access_token": "fresh-secret-tok", "expires_in": 3600}

        monkeypatch.setattr(oauth_discovery, "_send", lambda *a, **k: _FakeTokenResp())
        monkeypatch.setattr(oauth_discovery, "_require_success", lambda r: None)

        seen_auth = []
        seen_urls = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_urls.append(str(request.url))
            seen_auth.append(request.headers.get("Authorization"))
            if len(seen_auth) == 1:
                return httpx.Response(
                    401, headers={"WWW-Authenticate": 'Bearer error="invalid_token"'}
                )
            return httpx.Response(200, json={"ok": True})

        auth = _build_httpx_oauth(url, options={"name": "github", "auth_storage": storage})
        assert auth is not None

        with caplog.at_level("DEBUG"):
            async def run():
                async with httpx.AsyncClient(
                    transport=httpx.MockTransport(handler), auth=auth
                ) as client:
                    return await client.post(url, json={"jsonrpc": "2.0", "id": 1})

            resp = asyncio.run(run())

        assert resp.status_code == 200
        assert seen_auth == ["Bearer old-secret-tok", "Bearer fresh-secret-tok"]
        assert all("secret-tok" not in u for u in seen_urls)
        assert "old-secret-tok" not in caplog.text
        assert "fresh-secret-tok" not in caplog.text
        assert "ref-secret-tok" not in caplog.text
        assert storage.get_for_url("github", url)["tokens"]["access_token"] == "fresh-secret-tok"
        if os.name != "nt":
            assert ((tmp_path / "mcp-auth.json").stat().st_mode & 0o777) == 0o600

    def test_401_retries_at_most_once(self, tmp_path, monkeypatch):
        from praisonaiagents.mcp import oauth_discovery
        from praisonaiagents.mcp.mcp_http_stream import _build_httpx_oauth

        url = "https://mcp.example/mcp"
        storage = _make_storage(tmp_path)
        storage.set_client_info("github", {"client_id": "cid-1"}, server_url=url)
        storage.set_tokens(
            "github",
            {
                "access_token": "old-tok",
                "refresh_token": "ref-tok",
                "token_endpoint": "https://auth.example/token",
            },
            server_url=url,
        )

        class _FakeTokenResp:
            status_code = 200

            def json(self):
                return {"access_token": "fresh-tok", "expires_in": 3600}

        monkeypatch.setattr(oauth_discovery, "_send", lambda *a, **k: _FakeTokenResp())
        monkeypatch.setattr(oauth_discovery, "_require_success", lambda r: None)

        attempts = []

        def always_401(request: httpx.Request) -> httpx.Response:
            attempts.append(request.headers.get("Authorization"))
            return httpx.Response(401, headers={"WWW-Authenticate": "Bearer"})

        auth = _build_httpx_oauth(url, options={"name": "github", "auth_storage": storage})

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(always_401), auth=auth
            ) as client:
                return await client.post(url, json={})

        resp = asyncio.run(run())
        assert resp.status_code == 401
        assert attempts == ["Bearer old-tok", "Bearer fresh-tok"]

    @pytest.mark.parametrize("ci_val,is_tty", [("", False), ("true", True), ("1", True)])
    def test_401_non_tty_or_ci_raises_interactive_auth_required_no_browser(
        self, tmp_path, monkeypatch, ci_val, is_tty
    ):
        from praisonaiagents.errors import PraisonAIError
        from praisonaiagents.mcp import oauth_provider
        from praisonaiagents.mcp.mcp_http_stream import _build_httpx_oauth
        from praisonaiagents.mcp.oauth_provider import InteractiveAuthRequired

        if ci_val:
            monkeypatch.setenv("CI", ci_val)
        else:
            monkeypatch.delenv("CI", raising=False)
            monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setattr(
            "sys.stdin", type("_FakeStdin", (), {"isatty": lambda self: is_tty})()
        )

        browser_called = []
        monkeypatch.setattr(
            oauth_provider.webbrowser, "open", lambda u: browser_called.append(u) or True
        )

        url = "https://mcp.example/mcp"
        storage = _make_storage(tmp_path)
        auth = _build_httpx_oauth(
            url, options={"name": "linear", "oauth": True, "auth_storage": storage}
        )
        assert auth is not None

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, headers={"WWW-Authenticate": "Bearer"})

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), auth=auth
            ) as client:
                await client.post(url, json={})

        with pytest.raises(InteractiveAuthRequired) as exc_info:
            asyncio.run(run())

        assert isinstance(exc_info.value, PraisonAIError)
        assert "praisonai mcp auth linear" in str(exc_info.value)
        assert browser_called == []

    def test_401_with_tty_runs_interactive_flow_and_retries(self, tmp_path, monkeypatch):
        from praisonaiagents.mcp.mcp_http_stream import _build_httpx_oauth
        from praisonaiagents.mcp.oauth_provider import MCPOAuthProvider

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setattr(
            "sys.stdin", type("_FakeStdin", (), {"isatty": lambda self: True})()
        )

        captured_www = []

        def fake_ensure(self, www_authenticate=None, timeout=10.0):
            captured_www.append(www_authenticate)
            assert self.open_browser is True
            return "interactive-tok"

        monkeypatch.setattr(MCPOAuthProvider, "ensure_authenticated", fake_ensure)

        url = "https://mcp.example/mcp"
        storage = _make_storage(tmp_path)
        auth = _build_httpx_oauth(
            url, options={"name": "notion", "oauth": True, "auth_storage": storage}
        )

        seen_auth = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers.get("Authorization"))
            if len(seen_auth) == 1:
                return httpx.Response(
                    401,
                    headers={"WWW-Authenticate": 'Bearer resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"'},
                )
            return httpx.Response(200, json={"ok": True})

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), auth=auth
            ) as client:
                return await client.post(url, json={})

        resp = asyncio.run(run())
        assert resp.status_code == 200
        assert seen_auth == [None, "Bearer interactive-tok"]
        assert captured_www == [
            'Bearer resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"'
        ]

    def test_http_stream_client_passes_auth_to_streamablehttp_client(self, tmp_path):
        from praisonaiagents.mcp import mcp_http_stream

        url = "https://mcp.example/mcp"
        storage = _make_storage(tmp_path)
        storage.set_tokens("gh", {"access_token": "tok-1"}, server_url=url)

        captured = []

        class _FakeSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            async def initialize(self):
                return None

            async def list_tools(self):
                return type("_R", (), {"tools": []})()

        class _FakeStreams:
            async def __aenter__(self):
                return (None, None, None)

            async def __aexit__(self, *a):
                return None

        def fake_streamable(**kw):
            captured.append(kw)
            return _FakeStreams()

        with patch.object(mcp_http_stream, "streamablehttp_client", fake_streamable), \
             patch.object(mcp_http_stream, "ClientSession", lambda r, w: _FakeSession()):
            client = mcp_http_stream.HTTPStreamMCPClient(
                url, options={"auth_storage": storage}
            )
            client.close()

        assert len(captured) == 1
        assert isinstance(captured[0].get("auth"), httpx.Auth)
