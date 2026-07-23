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


def test_bind_failure_parameter_hint_reaches_model_via_public_path():
    # Greptile P1: the parameter hint must survive conversion to
    # ToolExecutionError (which keeps only the message) so the model can retry
    # with the right arguments instead of only seeing the raw error.
    def web_search(query: str, limit: int = 10) -> str:
        """Search the web."""
        raise TypeError("missing a required argument: 'query'")

    from praisonaiagents.errors import ToolExecutionError

    agent = _make_agent([web_search])

    with pytest.raises(ToolExecutionError) as exc:
        agent.execute_tool("web_search", {})
    msg = str(exc.value)
    assert "query" in msg
    assert "limit" in msg


class _FakeMCPTool:
    def __init__(self, name):
        self.__name__ = name
        self.name = name

    def __call__(self, **kwargs):
        return f"{self.__name__}:{kwargs}"


def _make_fake_mcp(tool_names):
    from praisonaiagents.mcp.mcp import MCP

    class _StubMCP(MCP):
        def __init__(self, names):
            self._tools = [_FakeMCPTool(n) for n in names]

        def __iter__(self):
            return iter(self._tools)

    return _StubMCP(tool_names)


def test_mcp_tool_name_appears_in_inventory():
    # Greptile P1: MCP-contained tools must appear in the corrective inventory
    # instead of the opaque container (which previously yielded []).
    agent = _make_agent([_make_fake_mcp(["read_file", "write_file"])])

    result = agent._execute_tool_impl("totally_made_up_tool", {})
    assert isinstance(result, dict)
    assert set(result["available_tools"]) == {"read_file", "write_file"}


def test_mcp_tool_name_repairs_case_and_separator():
    # Greptile P1: a case/separator-drifted MCP tool name should self-repair
    # and dispatch to the real MCP tool rather than falling through.
    agent = _make_agent([_make_fake_mcp(["read_file"])])

    result = agent._execute_tool_impl("Read-File", {"path": "x"})
    assert result == "read_file:{'path': 'x'}"
