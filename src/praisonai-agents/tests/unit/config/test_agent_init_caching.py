"""G-19, first block: Agent(caching=...) resolution moved out of __init__ into a
pure function. Expected values were recorded on main before the move."""

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_caching
from praisonaiagents.config.feature_configs import CachingConfig

# value -> (cache, prompt_caching), as Agent resolved them on main
EXPECTED = [
    (None, (True, None)),
    (False, (False, None)),
    (True, (True, None)),
    (CachingConfig(), (True, None)),
    (CachingConfig(enabled=False, prompt_caching=True), (False, True)),
    ("enabled", (True, None)),
    ("disabled", (False, None)),
    ("prompt", (True, True)),
    ({"enabled": False}, (False, None)),
]


@pytest.mark.parametrize("value,expected", EXPECTED, ids=[repr(v)[:30] for v, _ in EXPECTED])
def test_function_matches_recorded_behaviour(value, expected):
    config, cache, prompt_caching = resolve_agent_caching(value)
    assert (cache, prompt_caching) == expected
    assert config is None if value is False else isinstance(config, CachingConfig)


@pytest.mark.parametrize("value,expected", EXPECTED, ids=[repr(v)[:30] for v, _ in EXPECTED])
def test_agent_still_resolves_the_same(value, expected, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="hi", caching=value)
    assert (agent.cache, agent.prompt_caching) == expected


def test_config_object_is_passed_through_unchanged():
    cfg = CachingConfig(enabled=False, prompt_caching=True)
    assert resolve_agent_caching(cfg)[0] is cfg
