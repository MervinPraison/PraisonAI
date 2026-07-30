"""
Tests for serving PraisonAI agents to MCP clients (issue #3528).

Covers the agent adapter surface:
  - one ``ask_{name}`` tool published per agent, plus ``list_agents``
  - session continuity: same ``session_id`` sees prior turns; omitted id mints a
    fresh id and shares no history
  - no tool parameter lets the client set instructions/persona
"""

import asyncio

import pytest

from praisonai_mcp.mcp_server.registry import MCPToolRegistry
from praisonai_mcp.mcp_server.agent_adapter import register_agents


class FakeAgent:
    """Minimal Agent stand-in exposing name + achat + chat_history."""

    def __init__(self, name, reply="ok"):
        self.name = name
        self.instructions = f"You are {name}."
        self.reply = reply
        self.chat_history = []
        self.seen_histories = []

    async def achat(self, message):
        # Record the history the turn started with (for continuity assertions).
        self.seen_histories.append(list(self.chat_history))
        return f"{self.name}:{self.reply}:{message}"


class Server:
    def __init__(self):
        self._tool_registry = MCPToolRegistry()


def _call(registry, name, **kwargs):
    tool = registry.get(name)
    assert tool is not None, f"tool {name} not registered"
    result = tool.handler(**kwargs)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return result


def test_ask_agent_tool_published_per_agent():
    server = Server()
    register_agents(server, [FakeAgent("support"), FakeAgent("billing")])

    names = {t.name for t in server._tool_registry.list_all()}
    assert "ask_support" in names
    assert "ask_billing" in names
    assert "list_agents" in names


def test_list_agents_lists_names_and_descriptions():
    server = Server()
    register_agents(server, [FakeAgent("support")])
    out = _call(server._tool_registry, "list_agents")
    assert out["agents"][0]["name"] == "support"


def test_session_continuity_same_id_sees_history():
    agent = FakeAgent("support")
    server = Server()
    register_agents(server, [agent])

    first = _call(server._tool_registry, "ask_support", message="hi", session_id="s1")
    assert first["structuredContent"]["session_id"] == "s1"

    _call(server._tool_registry, "ask_support", message="again", session_id="s1")

    # Second turn must start with the first turn's user+assistant messages.
    second_start = agent.seen_histories[1]
    assert any(m["content"] == "hi" for m in second_start)


def test_omitted_session_mints_fresh_id_and_no_shared_history():
    agent = FakeAgent("support")
    server = Server()
    register_agents(server, [agent])

    r1 = _call(server._tool_registry, "ask_support", message="one")
    r2 = _call(server._tool_registry, "ask_support", message="two")

    id1 = r1["structuredContent"]["session_id"]
    id2 = r2["structuredContent"]["session_id"]
    assert id1 and id2 and id1 != id2

    # No shared history: each fresh session starts empty.
    assert agent.seen_histories[0] == []
    assert agent.seen_histories[1] == []


def test_no_client_instructions_parameter():
    server = Server()
    register_agents(server, [FakeAgent("support")])
    schema = server._tool_registry.get("ask_support").to_mcp_schema()
    props = schema["inputSchema"]["properties"]
    assert "instructions" not in props
    assert set(props) <= {"message", "session_id", "user_id"}
    assert schema["inputSchema"]["required"] == ["message"]


def test_same_session_id_across_agents_does_not_leak_history():
    support = FakeAgent("support")
    billing = FakeAgent("billing")
    server = Server()
    register_agents(server, [support, billing])

    # Reuse the SAME client-supplied session id across two different agents.
    _call(server._tool_registry, "ask_support", message="hi support", session_id="shared")
    _call(server._tool_registry, "ask_billing", message="hi billing", session_id="shared")

    # Billing's turn must start empty — it must not see support's transcript.
    assert billing.seen_histories[0] == []


def test_normalized_name_collision_registers_distinct_tools():
    server = Server()
    # "Support" and "support" normalize to the same suffix; both must survive.
    register_agents(server, [FakeAgent("Support"), FakeAgent("support")])

    names = {t.name for t in server._tool_registry.list_all()}
    assert "ask_support" in names
    assert "ask_support_2" in names


def test_unnamed_agents_do_not_collide():
    server = Server()
    a = FakeAgent("support")
    a.name = None
    b = FakeAgent("billing")
    b.name = None
    register_agents(server, [a, b])

    names = {t.name for t in server._tool_registry.list_all()}
    assert "ask_agent" in names
    assert "ask_agent_2" in names


def test_serve_agents_rejects_unknown_transport():
    from praisonai_mcp import serve_agents

    with pytest.raises(ValueError):
        serve_agents([FakeAgent("support")], transport="websocket")
