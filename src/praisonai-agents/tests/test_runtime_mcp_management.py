"""Tests for runtime MCP server management on Agent.

These tests use a lightweight fake MCP object so they do not require a live
MCP server or the optional ``mcp`` package to be installed.
"""

import asyncio

import pytest

from praisonaiagents import Agent


class FakeMCP:
    """Minimal stand-in for an MCP instance (iterable of tool callables)."""

    def __init__(self, name):
        self._name = name
        self.shutdown_called = False

        def _tool():
            return f"{name}-result"

        _tool.__name__ = f"{name}_tool"
        self._tools = [_tool]

    def __iter__(self):
        return iter(self._tools)

    def get_tools(self):
        return self._tools

    def shutdown(self):
        self.shutdown_called = True


def _make_agent():
    return Agent(instructions="test", llm="gpt-4o-mini")


def test_add_mcp_server_makes_tools_available():
    agent = _make_agent()
    mcp = FakeMCP("notion")

    agent.add_mcp_server("notion", mcp)

    assert "notion" in agent.list_mcp_servers()
    assert mcp in agent.tools


def test_add_duplicate_name_raises():
    agent = _make_agent()
    agent.add_mcp_server("notion", FakeMCP("notion"))

    with pytest.raises(ValueError):
        agent.add_mcp_server("notion", FakeMCP("notion2"))


def test_add_empty_name_raises():
    agent = _make_agent()
    with pytest.raises(ValueError):
        agent.add_mcp_server("", FakeMCP("x"))


def test_remove_mcp_server_disconnects_and_deregisters():
    agent = _make_agent()
    mcp = FakeMCP("notion")
    agent.add_mcp_server("notion", mcp)

    removed = agent.remove_mcp_server("notion")

    assert removed is True
    assert mcp.shutdown_called is True
    assert mcp not in agent.tools
    assert "notion" not in agent.list_mcp_servers()


def test_remove_unknown_returns_false():
    agent = _make_agent()
    assert agent.remove_mcp_server("nope") is False


def test_refresh_tools_returns_current_tools():
    agent = _make_agent()
    mcp = FakeMCP("notion")
    agent.add_mcp_server("notion", mcp)

    tools = agent.refresh_tools()
    assert mcp in tools


def test_add_normalizes_non_list_tools():
    agent = Agent(instructions="test", llm="gpt-4o-mini")
    # Force a non-list tools attribute to exercise normalization
    agent.tools = ()
    mcp = FakeMCP("notion")

    agent.add_mcp_server("notion", mcp)

    assert isinstance(agent.tools, list)
    assert mcp in agent.tools


def test_add_remove_cycle_allows_reattach():
    agent = _make_agent()
    agent.add_mcp_server("notion", FakeMCP("notion"))
    agent.remove_mcp_server("notion")
    # Should be able to attach again under the same name
    agent.add_mcp_server("notion", FakeMCP("notion"))
    assert "notion" in agent.list_mcp_servers()


def test_close_shuts_down_runtime_mcp_servers():
    agent = _make_agent()
    mcp = FakeMCP("notion")
    agent.add_mcp_server("notion", mcp)

    agent.close()

    assert mcp.shutdown_called is True
    assert agent.list_mcp_servers() == []


def test_aclose_shuts_down_runtime_mcp_servers():
    agent = _make_agent()
    mcp = FakeMCP("notion")
    agent.add_mcp_server("notion", mcp)

    asyncio.run(agent.aclose())

    assert mcp.shutdown_called is True
    assert agent.list_mcp_servers() == []


def test_close_continues_after_one_shutdown_failure():
    agent = _make_agent()
    failing = FakeMCP("bad")

    def _boom():
        raise RuntimeError("shutdown failed")

    failing.shutdown = _boom
    good = FakeMCP("good")

    agent.add_mcp_server("bad", failing)
    agent.add_mcp_server("good", good)

    # One failure must not abort the rest, and the registry is cleared.
    agent.close()

    assert good.shutdown_called is True
    assert agent.list_mcp_servers() == []
