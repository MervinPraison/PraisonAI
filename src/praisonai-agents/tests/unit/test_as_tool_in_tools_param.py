"""as_tool() must work where its own docstring says to use it: tools=[...]."""
import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.handoff import Handoff


def _llm_tool_names(agent):
    return sorted(f["function"]["name"] for f in agent._format_tools_for_completion())


def test_as_tool_returns_a_handoff():
    coder = Agent(name="Coder", instructions="Write Python code")
    assert isinstance(coder.as_tool("Write code"), Handoff)


def test_docstring_example_exposes_both_agents_to_the_llm():
    researcher = Agent(name="Researcher", instructions="Research topics")
    coder = Agent(name="Coder", instructions="Write Python code")
    writer = Agent(
        name="Writer",
        tools=[
            researcher.as_tool("Research a topic and return findings"),
            coder.as_tool("Write Python code for a given task"),
        ],
    )
    assert _llm_tool_names(writer) == ["invoke_coder", "invoke_researcher"]
    assert not any(isinstance(t, Handoff) for t in writer.tools)


def test_as_tool_is_dispatchable_by_name():
    coder = Agent(name="Coder", instructions="Write Python code")
    coder.chat = lambda *a, **k: "def f(): pass"
    writer = Agent(name="Writer", tools=[coder.as_tool("Write code")])
    result = writer.execute_tool("invoke_coder", {"prompt": "write f"})
    assert "not found" not in str(result)


def test_custom_tool_name_is_honoured():
    coder = Agent(name="Coder", instructions="Write Python code")
    writer = Agent(
        name="Writer",
        tools=[coder.as_tool("Write code", tool_name="delegate_to_coder")],
    )
    assert _llm_tool_names(writer) == ["delegate_to_coder"]


def test_handoffs_param_is_unaffected():
    coder = Agent(name="Coder", instructions="Write Python code")
    writer = Agent(name="Writer", handoffs=[coder])
    assert _llm_tool_names(writer) == ["transfer_to_coder"]
