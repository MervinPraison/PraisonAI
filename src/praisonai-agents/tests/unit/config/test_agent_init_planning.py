"""G-19, block 3: Agent(planning=...) resolution as a pure function.
Expected values were recorded on main before the move."""

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_planning
from praisonaiagents.config.feature_configs import PlanningConfig

ATTRS = ("planning", "planning_tools", "planning_reasoning", "plan_mode")
EXPECTED = [
    (None, (False, None, False, False)),
    (False, (False, None, False, False)),
    (True, (True, None, False, False)),
    (PlanningConfig(reasoning=True, read_only=True), (True, None, True, True)),
    ("reasoning", (True, None, True, False)),
    ("read_only", (True, None, False, True)),
    ("auto", (True, None, False, False)),
    ({"reasoning": True}, (True, None, True, False)),
]
IDS = [repr(v)[:30] for v, _ in EXPECTED]


@pytest.mark.parametrize("value,expected", EXPECTED, ids=IDS)
def test_agent_still_resolves_the_same(value, expected, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="hi", planning=value)
    assert tuple(getattr(agent, a) for a in ATTRS) == expected


def test_unknown_string_still_raises():
    with pytest.raises(ValueError, match="Invalid planning value"):
        resolve_agent_planning("gpt-4o")


def test_none_sets_only_planning_false():
    assert resolve_agent_planning(None) == (None, {"planning": False})
    assert resolve_agent_planning(True)[1]["planning"] is True
