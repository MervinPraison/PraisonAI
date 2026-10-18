"""Disabled handoffs do not load their implementation; enabled paths still convert."""
import sys

import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.handoff import Handoff


def make_agent(name, **kwargs):
    return Agent(
        name=name,
        instructions="Return a short answer.",
        api_key="synthetic-offline-fixture",
        reflection=False,
        memory=False,
        knowledge=False,
        **kwargs,
    )


@pytest.mark.parametrize("tools", [None, []])
def test_disabled_handoffs_do_not_require_handoff_module(monkeypatch, tools):
    # A blocked import makes an unnecessary local import observable even when
    # another test has already loaded this module in the same interpreter.
    monkeypatch.setitem(sys.modules, "praisonaiagents.agent.handoff", None)
    agent = make_agent("no-handoff", tools=tools)
    assert agent.tools == []
    assert agent.handoffs == []


@pytest.mark.parametrize("entry", ["tools", "handoffs"])
def test_handoff_objects_still_convert_to_bound_tools(entry):
    target = make_agent("target")
    source = Handoff(target)
    agent = make_agent("parent", **{entry: [source]})
    assert len(agent.tools) == 1
    assert callable(agent.tools[0])
    assert agent.tools[0]._praison_handoff_source is source


def test_direct_agent_handoff_still_converts_to_bound_tool():
    target = make_agent("target")
    agent = make_agent("parent", handoffs=[target])
    assert len(agent.tools) == 1
    assert callable(agent.tools[0])
    assert agent.tools[0]._praison_handoff_source.agent is target


def test_regular_tool_is_unchanged():
    def echo(text: str) -> str:
        """Return the input text."""
        return text

    agent = make_agent("regular-tool", tools=[echo])
    assert agent.tools == [echo]
