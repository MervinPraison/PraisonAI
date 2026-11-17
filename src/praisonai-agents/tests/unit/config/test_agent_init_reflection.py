"""G-19, block 4: Agent(reflection=...) resolution as a pure function.
Expected values were recorded on main before the move."""

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_reflection
from praisonaiagents.config.feature_configs import ReflectionConfig

ATTRS = ("self_reflect", "min_reflect", "max_reflect", "reflect_llm", "reflect_prompt")
EXPECTED = [
    (None, (False, 1, 3, "gpt-4o-mini", None)),
    (False, (False, 1, 3, "gpt-4o-mini", None)),
    (True, (True, 1, 3, "gpt-4o-mini", None)),
    (ReflectionConfig(min_iterations=2, max_iterations=4, llm="gpt-4o", prompt="P"), (True, 2, 4, "gpt-4o", "P")),
    ("minimal", (True, 1, 1, "gpt-4o-mini", None)),
    ("standard", (True, 1, 3, "gpt-4o-mini", None)),
    ("thorough", (True, 2, 5, "gpt-4o-mini", None)),
    ({"max_iterations": 5}, (True, 1, 5, "gpt-4o-mini", None)),
]
IDS = [repr(v)[:30] for v, _ in EXPECTED]


@pytest.mark.parametrize("value,expected", EXPECTED, ids=IDS)
def test_agent_still_resolves_the_same(value, expected, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="hi", reflection=value)
    assert tuple(getattr(agent, a) for a in ATTRS) == expected


def test_none_sets_nothing():
    assert resolve_agent_reflection(None) == (None, {})
    assert resolve_agent_reflection(False) == (None, {"self_reflect": False})
