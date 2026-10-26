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
