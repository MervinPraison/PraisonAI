"""Tests for agent-runtime self-repair and actionable feedback on
unknown or malformed tool calls (issue #3309)."""

import pytest

from praisonaiagents import Agent


def _make_agent(tools):
    return Agent(
        name="Repair",
        instructions="test",
        tools=tools,
        llm="gpt-4o-mini",
    )


def test_miscased_tool_name_auto_resolves():
    def web_search(query: str) -> str:
        """Search the web."""
        return f"results for {query}"

    agent = _make_agent([web_search])

    result = agent.execute_tool("WebSearch", {"query": "hello"})
    assert result == "results for hello"


def test_separator_drift_auto_resolves():
    def web_search(query: str) -> str:
        """Search the web."""
        return f"results for {query}"

    agent = _make_agent([web_search])

    result = agent.execute_tool("web-search", {"query": "world"})
    assert result == "results for world"


def test_unknown_tool_returns_available_inventory():
    def web_search(query: str) -> str:
        """Search the web."""
        return query

    def calculator(a: int, b: int) -> int:
        """Add numbers."""
        return a + b

    agent = _make_agent([web_search, calculator])

    # The corrective dict is produced by the dispatch impl; the public
    # execute_tool() wrapper escalates it as a ToolExecutionError whose message
    # carries the same actionable text back to the model.
    result = agent._execute_tool_impl("totally_made_up_tool", {})
    assert isinstance(result, dict)
    assert "not found" in result["error"]
    assert set(result["available_tools"]) == {"web_search", "calculator"}


def test_unknown_tool_suggests_nearest():
    def web_search(query: str) -> str:
        """Search the web."""
        return query

    agent = _make_agent([web_search])

    result = agent._execute_tool_impl("web_serch", {"query": "x"})
    assert isinstance(result, dict)
    assert "web_search" in result["error"]


def test_argument_bind_failure_echoes_schema():
    def web_search(query: str, limit: int = 10) -> str:
        """Search the web."""
        raise TypeError("missing required argument: 'query'")

    agent = _make_agent([web_search])

    result = agent._execute_tool_impl("web_search", {})
    assert isinstance(result, dict)
    assert "expected_parameters" in result
    assert "query" in result["expected_parameters"]["required"]
    assert "limit" in result["expected_parameters"]["optional"]


def test_unknown_tool_message_reaches_model_via_public_path():
    def web_search(query: str) -> str:
        """Search the web."""
        return query

    from praisonaiagents.errors import ToolExecutionError

    agent = _make_agent([web_search])

    with pytest.raises(ToolExecutionError) as exc:
        agent.execute_tool("totally_made_up_tool", {})
    assert "not found" in str(exc.value)
    assert "web_search" in str(exc.value)
