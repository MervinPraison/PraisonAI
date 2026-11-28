"""Gateway ``mcp_servers:`` shares one pooled MCP client across agents (Issue #6004)."""

import praisonaiagents

from praisonai_bot.gateway import WebSocketGateway


def _fake_mcp_factory(calls, shutdowns=None):
    def fake_mcp(target, **opts):
        calls.append((target, opts))

        def downstream_tool(query: str) -> str:
            """Fake downstream MCP tool."""
            return query

        def with_tool_prefix(prefix):
            downstream_tool.prefix = prefix
            return downstream_tool

        downstream_tool.with_tool_prefix = with_tool_prefix
        downstream_tool.shutdown = lambda: (shutdowns if shutdowns is not None else []).append(target)
        return downstream_tool

    return fake_mcp


def test_mcp_server_opened_once_and_shared(monkeypatch):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    gw = WebSocketGateway()
    mcp_cfg = {"github": {"command": "npx", "args": ["-y", "server-github"]}}
    agents_cfg = {
        "a": {"instructions": "x", "model": "gpt-4o-mini", "tools": ["github"]},
        "b": {"instructions": "y", "model": "gpt-4o-mini", "tools": ["github"]},
        "c": {"instructions": "z", "model": "gpt-4o-mini"},
    }

    gw._create_agents_from_config(agents_cfg, mcp_servers_cfg=mcp_cfg)
    # A reload with the same spec reuses the pooled client.
    gw._create_agents_from_config(agents_cfg, mcp_servers_cfg=mcp_cfg)

    assert calls == [("npx", {"args": ["-y", "server-github"]})]
    shared = next(iter(gw._mcp_pool.values()))
    assert shared in gw.get_agent("a").tools
    assert shared in gw.get_agent("b").tools
    assert shared not in (gw.get_agent("c").tools or [])
    # Tools are namespaced by server name so two servers cannot collide.
    assert shared.prefix == "github"


def test_mcp_server_spec_change_opens_new_client(monkeypatch):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    gw = WebSocketGateway()
    agents_cfg = {"a": {"instructions": "x", "model": "gpt-4o-mini", "tools": ["search"]}}

    gw._create_agents_from_config(agents_cfg, mcp_servers_cfg={"search": {"url": "http://h/sse"}})
    gw._create_agents_from_config(agents_cfg, mcp_servers_cfg={"search": {"url": "http://h2/sse"}})

    assert [c[0] for c in calls] == ["http://h/sse", "http://h2/sse"]


def test_bad_mcp_server_is_skipped(monkeypatch):
    def boom(target, **opts):
        raise RuntimeError("cannot start")

    monkeypatch.setattr(praisonaiagents, "MCP", boom, raising=False)
    gw = WebSocketGateway()
    agents_cfg = {"a": {"instructions": "x", "model": "gpt-4o-mini", "tools": ["github", "nourl"]}}

    gw._create_agents_from_config(
        agents_cfg, mcp_servers_cfg={"github": {"command": "npx"}, "nourl": {}}
    )

    assert gw.get_agent("a") is not None
    assert gw._mcp_pool == {}


def test_prune_retires_unreferenced_clients(monkeypatch):
    calls, shutdowns = [], []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls, shutdowns), raising=False)
    gw = WebSocketGateway()

    gw._warm_mcp_pool({"a": {"url": "http://a/sse"}, "b": {"url": "http://b/sse"}})
    gw._prune_mcp_pool({"a": {"url": "http://a/sse"}})

    assert shutdowns == ["http://b/sse"]
    assert len(gw._mcp_pool) == 1
    gw._prune_mcp_pool(None)
    assert shutdowns == ["http://b/sse", "http://a/sse"]
    assert gw._mcp_pool == {}


def test_editor_field_aliases_supported(monkeypatch):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    gw = WebSocketGateway()

    client = gw._get_pooled_mcp(
        "docs",
        {
            "httpUrl": "https://mcp.example/mcp",
            "http_headers": {"Authorization": "Bearer tok"},
            "includeTools": ["read"],
            "excludeTools": ["delete"],
        },
    )

    assert client is not None
    assert client.prefix == "docs"
    assert calls == [(
        "https://mcp.example/mcp",
        {
            "args": None,
            "headers": {"Authorization": "Bearer tok"},
            "allowed_tools": ["read"],
            "disabled_tools": ["delete"],
        },
    )]


def test_disabled_server_is_skipped(monkeypatch):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    gw = WebSocketGateway()

    assert gw._get_pooled_mcp("off1", {"command": "npx", "enabled": False}) is None
    assert gw._get_pooled_mcp("off2", {"command": "npx", "disabled": True}) is None
    assert calls == []
    assert gw._mcp_pool == {}


def test_bad_url_never_starts_as_command(monkeypatch):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    gw = WebSocketGateway()

    assert gw._get_pooled_mcp("bad", {"url": "touch MARKER"}) is None
    assert calls == []
    assert gw._mcp_pool == {}


def test_legacy_sse_headers_handled_by_shared_builder(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    gw = WebSocketGateway()

    assert gw._get_pooled_mcp(
        "auth_sse",
        {"url": "https://mcp.example/sse", "headers": {"Authorization": "Bearer tok"}},
    ) is None
    assert calls == []

    with caplog.at_level("WARNING"):
        client = gw._get_pooled_mcp(
            "hdr_sse",
            {"url": "https://mcp.example/sse", "headers": {"X-Trace": "1"}},
        )
    assert client is not None
    assert "headers" not in calls[0][1]
    assert "SSE" in caplog.text


def test_does_not_double_expand_env_vars(monkeypatch):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    monkeypatch.setenv("SOME_SECRET", "s3cret-value")
    gw = WebSocketGateway()

    client = gw._get_pooled_mcp(
        "srv",
        {
            "url": "https://mcp.example/mcp",
            "headers": {"X": "${SOME_SECRET}", "Y": "${env:SOME_SECRET}"},
        },
    )

    assert client is not None
    assert calls[0][1]["headers"] == {"X": "${SOME_SECRET}", "Y": "${env:SOME_SECRET}"}
    assert "s3cret-value" not in repr(calls)


def test_command_as_list_and_ms_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(praisonaiagents, "MCP", _fake_mcp_factory(calls), raising=False)
    gw = WebSocketGateway()

    client = gw._get_pooled_mcp(
        "fs",
        {"command": ["npx", "-y", "pkg"], "args": ["/my docs"], "timeout": 30000},
    )

    assert client is not None
    assert client.prefix == "fs"
    assert calls == [("npx", {"args": ["-y", "pkg", "/my docs"], "timeout": 30.0})]
