"""Unit tests for wrapper MCP callers using the shared core config builder.

Verifies ``praisonai.capabilities.mcp`` (``mcp_list_tools``, ``mcp_call_tool``)
and ``praisonai.endpoints.providers.mcp.MCPProvider`` build clients via
``praisonaiagents.mcp.loader.build_mcp(..., cls=MCP)`` with ``expand_env=False``,
preserving ``praisonaiagents.mcp.MCP`` patching, argument lists, timeouts,
and URL/SSE validation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


def _make_fake_mcp_class(tools):
    """Return a fake MCP class that records constructor calls without spawning."""
    calls: list[tuple[tuple, dict]] = []

    class FakeMCP:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

        def get_tools(self):
            return list(tools)

    return FakeMCP, calls


def _fake_tool(name: str, description: str = "", fn=None):
    def _call(**kw):
        return fn(**kw) if fn else kw

    _call.name = name
    _call.description = description
    return _call


class TestCapabilitiesMcpSharedBuilder:
    def test_mcp_list_tools_uses_shared_builder_with_timeout_and_args(self):
        from praisonai.capabilities.mcp import mcp_list_tools

        tool = _fake_tool("read_file", "Read a file")
        FakeMCP, calls = _make_fake_mcp_class([tool])

        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            res = mcp_list_tools(
                "npx",
                args=["-y", "pkg", "/my docs"],
                env={"K": "v"},
                timeout=45.0,
            )

        assert res.tools == [{"name": "read_file", "description": "Read a file"}]
        assert res.server_name == "npx"
        assert len(calls) == 1
        pos, kw = calls[0]
        assert pos == ("npx",)
        assert kw["args"] == ["-y", "pkg", "/my docs"]
        assert kw["env"] == {"K": "v"}
        assert kw["timeout"] == 45.0

    def test_mcp_list_tools_default_timeout_and_no_env_expansion(self, monkeypatch):
        from praisonai.capabilities.mcp import mcp_list_tools

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        FakeMCP, calls = _make_fake_mcp_class([])

        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            mcp_list_tools(
                "npx",
                args=["${SOME_SECRET}"],
                env={"TOK": "${env:SOME_SECRET}"},
            )

        assert len(calls) == 1
        pos, kw = calls[0]
        assert pos == ("npx",)
        assert kw["args"] == ["${SOME_SECRET}"]
        assert kw["env"] == {"TOK": "${env:SOME_SECRET}"}
        assert kw["timeout"] == 30.0
        assert "s3cret-value" not in repr(calls)

    def test_mcp_list_tools_remote_url_and_sse_auth_refused(self):
        from praisonai.capabilities.mcp import mcp_list_tools

        FakeMCP, calls = _make_fake_mcp_class([])
        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            mcp_list_tools(
                "https://mcp.example/mcp",
                headers={"Authorization": "Bearer tok"},
                timeout=15.0,
            )
        assert len(calls) == 1
        assert calls[0][0] == ("https://mcp.example/mcp",)
        assert calls[0][1]["headers"] == {"Authorization": "Bearer tok"}
        assert calls[0][1]["timeout"] == 15.0

        FakeMCP2, calls2 = _make_fake_mcp_class([])
        with patch("praisonaiagents.mcp.MCP", FakeMCP2):
            with pytest.raises(ValueError, match="SSE"):
                mcp_list_tools(
                    "https://mcp.example/sse",
                    headers={"Authorization": "Bearer tok"},
                )
        assert calls2 == []

    def test_mcp_list_tools_rejects_bad_url_kwarg(self):
        from praisonai.capabilities.mcp import mcp_list_tools

        FakeMCP, calls = _make_fake_mcp_class([])
        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            with pytest.raises(ValueError, match="url"):
                mcp_list_tools("ignored", url="touch MARKER")
        assert calls == []

    def test_mcp_call_tool_uses_shared_builder_with_timeout_and_no_env_expansion(self, monkeypatch):
        from praisonai.capabilities.mcp import mcp_call_tool

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        tool = _fake_tool("echo", fn=lambda text: f"hi:{text}")
        FakeMCP, calls = _make_fake_mcp_class([tool])

        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            res = mcp_call_tool(
                "npx",
                "echo",
                tool_args={"text": "world"},
                args=["-y", "pkg", "${SOME_SECRET}"],
                env={"K": "${SOME_SECRET}"},
                timeout=75.0,
            )

        assert res.result == "hi:world"
        assert res.tool_name == "echo"
        assert len(calls) == 1
        pos, kw = calls[0]
        assert pos == ("npx",)
        assert kw["args"] == ["-y", "pkg", "${SOME_SECRET}"]
        assert kw["env"] == {"K": "${SOME_SECRET}"}
        assert kw["timeout"] == 75.0
        assert "s3cret-value" not in repr(calls)

    def test_async_wrappers_delegate_through_shared_builder(self):
        from praisonai.capabilities.mcp import amcp_call_tool, amcp_list_tools

        tool = _fake_tool("ping", "Ping", fn=lambda: "pong")
        FakeMCP, calls = _make_fake_mcp_class([tool])

        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            listed = asyncio.run(amcp_list_tools("npx", args=["-y", "p"], timeout=12.0))
            called = asyncio.run(amcp_call_tool("npx", "ping", args=["-y", "p"], timeout=22.0))

        assert listed.tools == [{"name": "ping", "description": "Ping"}]
        assert called.result == "pong"
        assert calls[0][1]["timeout"] == 12.0
        assert calls[1][1]["timeout"] == 22.0


class TestMCPProviderSharedBuilder:
    def test_list_stdio_tools_uses_shared_builder(self, monkeypatch):
        from praisonai.endpoints.providers.mcp import MCPProvider

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        tool = _fake_tool("search", "Search docs")
        FakeMCP, calls = _make_fake_mcp_class([tool])

        provider = MCPProvider(
            transport="stdio",
            command="npx",
            args=["-y", "pkg", "/my docs", "${SOME_SECRET}"],
            env={"K": "${SOME_SECRET}"},
            timeout=40.0,
        )
        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            endpoints = provider.list_endpoints()

        assert len(endpoints) == 1
        assert endpoints[0].name == "search"
        assert endpoints[0].description == "Search docs"
        assert len(calls) == 1
        pos, kw = calls[0]
        assert pos == ("npx",)
        assert kw["args"] == ["-y", "pkg", "/my docs", "${SOME_SECRET}"]
        assert kw["env"] == {"K": "${SOME_SECRET}"}
        assert kw["timeout"] == 40.0
        assert "s3cret-value" not in repr(calls)

    def test_invoke_stdio_uses_shared_builder(self, monkeypatch):
        from praisonai.endpoints.providers.mcp import MCPProvider

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        tool = _fake_tool("add", fn=lambda a, b: a + b)
        FakeMCP, calls = _make_fake_mcp_class([tool])

        provider = MCPProvider(
            transport="stdio",
            command="npx",
            args=["-y", "pkg", "${SOME_SECRET}"],
            env={"K": "${SOME_SECRET}"},
            timeout=55.0,
        )
        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            res = provider.invoke("add", {"a": 2, "b": 3})

        assert res.ok is True
        assert res.data == 5
        assert len(calls) == 1
        pos, kw = calls[0]
        assert pos == ("npx",)
        assert kw["args"] == ["-y", "pkg", "${SOME_SECRET}"]
        assert kw["env"] == {"K": "${SOME_SECRET}"}
        assert kw["timeout"] == 55.0
        assert "s3cret-value" not in repr(calls)

    def test_stdio_missing_command_handled_without_spawning(self):
        from praisonai.endpoints.providers.mcp import MCPProvider

        FakeMCP, calls = _make_fake_mcp_class([])
        provider = MCPProvider(transport="stdio", command=None)

        with patch("praisonaiagents.mcp.MCP", FakeMCP):
            assert provider.list_endpoints() == []
            res = provider.invoke("anything")

        assert res.ok is False
        assert res.status == "error"
        assert calls == []
