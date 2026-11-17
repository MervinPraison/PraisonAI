"""G-19, block 2: Agent(templates=...) resolution as a pure function.
Expected values were recorded on main before the move."""

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_templates
from praisonaiagents.config.feature_configs import TemplateConfig

# value -> (system_template, prompt_template, response_template, use_system_prompt)
EXPECTED = [
    (None, (None, None, None, True)),
    (TemplateConfig(system="S {role}"), ("S {role}", None, None, True)),
    (TemplateConfig(prompt="P", response="R", use_system_prompt=False), (None, "P", "R", False)),
    ({"system": "D"}, ("D", None, None, True)),
    ("inline-string", (None, None, None, True)),  # ignored today, kept as is
    (123, (None, None, None, True)),
]
IDS = [repr(v)[:30] for v, _ in EXPECTED]


@pytest.mark.parametrize("value,expected", EXPECTED, ids=IDS)
def test_function_matches_recorded_behaviour(value, expected):
    assert resolve_agent_templates(value)[1:] == expected


@pytest.mark.parametrize("value,expected", EXPECTED, ids=IDS)
def test_agent_still_resolves_the_same(value, expected, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    a = Agent(name="a", instructions="hi", templates=value)
    assert (a.system_template, a.prompt_template, a.response_template, a.use_system_prompt) == expected


def test_config_object_is_passed_through():
    cfg = TemplateConfig(system="S")
    assert resolve_agent_templates(cfg)[0] is cfg
