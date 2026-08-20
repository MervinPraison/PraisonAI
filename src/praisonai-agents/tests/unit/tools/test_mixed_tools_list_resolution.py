"""A callable in tools=[...] must not stop the name strings from resolving."""
import pytest

from praisonaiagents import Agent
from praisonaiagents.tools.resolver import ToolResolutionError


def my_tool(x: str) -> str:
    """A local tool."""
    return "local:" + x


def _llm_tool_names(agent):
    return sorted(f["function"]["name"] for f in agent._format_tools_for_completion())


@pytest.mark.parametrize(
    "tools",
    [
        ["read_file"],
        [my_tool, "read_file"],
        ["read_file", my_tool],
    ],
    ids=["names_only", "callable_first", "name_first"],
)
def test_named_tool_is_resolved_in_any_list_shape(tools):
    agent = Agent(instructions="x", tools=tools)
    assert "read_file" in _llm_tool_names(agent)
    # Resolved to the real callable, not left as the bare string.
    assert not any(isinstance(t, str) for t in agent.tools)


def test_named_tool_is_dispatchable_alongside_a_callable():
    agent = Agent(instructions="x", tools=[my_tool, "read_file"])
    result = agent.execute_tool("read_file", {"filepath": "/etc/hostname"})
    # Reaches FileTools.read_file (which refuses the traversal) instead of
    # raising "Tool 'read_file' not found".
    assert isinstance(result, str)
    assert "not found" not in result
    assert agent.execute_tool("my_tool", {"x": "hi"}) == "local:hi"


def test_unknown_name_in_a_mixed_list_is_dropped_like_an_all_names_list():
    agent = Agent(instructions="x", tools=[my_tool, "no_such_tool"])
    assert _llm_tool_names(agent) == ["my_tool"]
    assert agent.tools == [my_tool]


def test_resolve_tools_list_preserves_non_string_entries_positionally():
    from praisonaiagents.tools.resolver import resolve_tools_list

    sentinel = object()
    out = resolve_tools_list([sentinel, "read_file", my_tool])
    assert out[0] is sentinel
    assert out[2] is my_tool
    assert getattr(out[1], "__name__", None) == "read_file"


def test_resolve_tools_list_is_strict_on_demand():
    from praisonaiagents.tools.resolver import resolve_tools_list

    with pytest.raises(ToolResolutionError):
        resolve_tools_list([my_tool, "no_such_tool"], strict=True)
