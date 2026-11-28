"""End-to-end wiring tests for OAuth from MCP.from_config -> MCP -> HTTPStreamMCPClient."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

httpx = pytest.importorskip("httpx")


def _fake_streamable_env():
    """Patch streamablehttp_client and ClientSession so HTTPStreamMCPClient never hits network."""
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

    return captured, fake_streamable, _FakeSession


class TestMCPOAuthWiring:
    def test_from_config_passes_oauth_and_server_name_without_old_warning(self, caplog):
        from praisonaiagents.mcp import MCP

        seen = []

        def fake_init(self, target=None, args=None, **kw):
            seen.append((target, args, kw))

        with caplog.at_level("WARNING"), patch.object(MCP, "__init__", fake_init):
            MCP.from_config(
                {"url": "https://api.example.com/mcp", "oauth": True},
                name="linear",
            )

        assert seen == [(
            "https://api.example.com/mcp",
            None,
            {"oauth": True, "server_name": "linear"},
        )]
        assert "not applied" not in caplog.text.lower()

    def test_from_config_oauth_dict_and_no_env_expansion_by_default(self, monkeypatch):
        from praisonaiagents.mcp import MCP

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        seen = []

        def fake_init(self, target=None, args=None, **kw):
            seen.append((target, args, kw))

        with patch.object(MCP, "__init__", fake_init):
            MCP.from_config(
                {
                    "url": "https://api.example.com/mcp",
                    "oauth": {"clientId": "cid-1", "scopes": ["read"]},
                    "headers": {"X-Tag": "${SOME_SECRET}"},
                },
                name="github",
            )

        assert len(seen) == 1
        assert seen[0][2]["oauth"] == {"client_id": "cid-1", "scopes": ["read"]}
        assert seen[0][2]["server_name"] == "github"
        assert seen[0][2]["headers"] == {"X-Tag": "${SOME_SECRET}"}
        assert "s3cret-value" not in repr(seen)

    def test_from_config_wires_stored_bearer_and_401_interactive_auth_required(
        self, tmp_path, monkeypatch, caplog
    ):
        from praisonaiagents.mcp import MCP, mcp_http_stream, oauth_provider
        from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
        from praisonaiagents.mcp.oauth_provider import InteractiveAuthRequired

        url = "https://api.example.com/mcp"
        monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(
            "sys.stdin", type("_FakeStdin", (), {"isatty": lambda self: False})()
        )
        browser_calls = []
        monkeypatch.setattr(
            oauth_provider.webbrowser, "open", lambda u: browser_calls.append(u) or True
        )

        # 1. With a stored token, MCP.from_config wires an httpx.Auth that attaches Bearer.
        storage = MCPAuthStorage()
        storage.set_tokens(
            "linear",
            {"access_token": "tok-linear-123", "expires_at": time.time() + 3600},
            server_url=url,
        )

        captured, fake_streamable, FakeSession = _fake_streamable_env()
        with caplog.at_level("WARNING"), \
             patch.object(mcp_http_stream, "streamablehttp_client", fake_streamable), \
             patch.object(mcp_http_stream, "ClientSession", lambda r, w: FakeSession()):
            client = MCP.from_config({"url": url, "oauth": True}, name="linear")
            client.http_stream_client.close()

        assert "not applied" not in caplog.text.lower()
        assert len(captured) == 1
        auth = captured[0].get("auth")
        assert isinstance(auth, httpx.Auth)

        sent_headers = []

        def ok_handler(request: httpx.Request) -> httpx.Response:
            sent_headers.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"ok": True})

        async def run_ok():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(ok_handler), auth=auth
            ) as hc:
                return await hc.post(url, json={})

        assert asyncio.run(run_ok()).status_code == 200
        assert sent_headers == ["Bearer tok-linear-123"]

        # 2. On 401 without refresh/TTY, raises InteractiveAuthRequired naming `praisonai mcp auth linear`.
        def unauth_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, headers={"WWW-Authenticate": "Bearer"})

        async def run_401():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(unauth_handler), auth=auth
            ) as hc:
                await hc.post(url, json={})

        with pytest.raises(InteractiveAuthRequired) as exc_info:
            asyncio.run(run_401())

        assert "praisonai mcp auth linear" in str(exc_info.value)
        assert browser_calls == []

    def test_explicit_authorization_header_takes_precedence_over_oauth(self, tmp_path, monkeypatch):
        from praisonaiagents.mcp import MCP, mcp_http_stream

        url = "https://api.example.com/mcp"
        monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))

        captured, fake_streamable, FakeSession = _fake_streamable_env()
        with patch.object(mcp_http_stream, "streamablehttp_client", fake_streamable), \
             patch.object(mcp_http_stream, "ClientSession", lambda r, w: FakeSession()):
            client = MCP.from_config(
                {
                    "url": url,
                    "oauth": True,
                    "headers": {"Authorization": "Bearer explicit-key"},
                },
                name="linear",
            )
            client.http_stream_client.close()

        assert len(captured) == 1
        assert captured[0]["headers"] == {"Authorization": "Bearer explicit-key"}
        assert "auth" not in captured[0]

    def test_direct_mcp_init_accepts_oauth_and_server_name(self, tmp_path, monkeypatch):
        from praisonaiagents.mcp import MCP, mcp_http_stream

        url = "https://api.example.com/mcp"
        monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praisonai"))

        captured, fake_streamable, FakeSession = _fake_streamable_env()
        with patch.object(mcp_http_stream, "streamablehttp_client", fake_streamable), \
             patch.object(mcp_http_stream, "ClientSession", lambda r, w: FakeSession()):
            client = MCP(url, oauth=True, server_name="notion")
            client.http_stream_client.close()

        assert len(captured) == 1
        assert isinstance(captured[0].get("auth"), httpx.Auth)

    def test_legacy_sse_url_with_oauth_warns_and_does_not_pass_oauth(self, caplog):
        from praisonaiagents.mcp import MCP

        seen = []

        def fake_init(self, target=None, args=None, **kw):
            seen.append((target, args, kw))

        with caplog.at_level("WARNING"), patch.object(MCP, "__init__", fake_init):
            MCP.from_config(
                {"url": "https://api.example.com/sse", "oauth": True},
                name="legacy",
            )

        assert seen == [("https://api.example.com/sse", None, {})]
        assert "sse" in caplog.text.lower()
