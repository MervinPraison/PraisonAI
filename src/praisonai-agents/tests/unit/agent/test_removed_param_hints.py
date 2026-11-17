"""D-05: a removed ``Agent`` parameter raises ``TypeError`` naming its replacement.

These flat parameters were grouped into config objects and are no longer
accepted. A bare "unexpected keyword argument" left the user to search the
signature; the error now says where each setting lives.
"""

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import (
    CachingConfig, ExecutionConfig, OutputConfig, ReflectionConfig, TemplateConfig, WebConfig,
)

REPLACEMENTS = {
    "verbose": ("output=", OutputConfig, "verbose"),
    "markdown": ("output=", OutputConfig, "markdown"),
    "stream": ("output=", OutputConfig, "stream"),
    "metrics": ("output=", OutputConfig, "metrics"),
    "self_reflect": ("reflection=", ReflectionConfig, None),
    "max_reflect": ("reflection=", ReflectionConfig, "max_iterations"),
    "min_reflect": ("reflection=", ReflectionConfig, "min_iterations"),
    "system_template": ("templates=", TemplateConfig, "system"),
    "cache": ("caching=", CachingConfig, "enabled"),
    "web_search": ("web=", WebConfig, "search"),
    "max_iter": ("execution=", ExecutionConfig, "max_iter"),
    "temperature": ("model=", None, "temperature"),
    "max_tokens": ("model=", None, "max_tokens"),
}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")


@pytest.mark.parametrize("name", sorted(REPLACEMENTS))
def test_removed_param_error_names_the_replacement(name):
    param, config, field = REPLACEMENTS[name]
    with pytest.raises(TypeError) as err:
        Agent(name="a", instructions="x", **{name: 1})
    message = str(err.value)
    assert name in message and param in message
    if field:
        assert field in message
    if config is not None and field:  # the hint must point at a field that exists
        assert field in config.__dataclass_fields__


def test_model_dict_carries_temperature_and_max_tokens():
    agent = Agent(name="a", instructions="x", model={"model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 50})
    assert (agent.llm_instance.temperature, agent.llm_instance.max_tokens) == (0.2, 50)


def test_unhinted_unknown_param_still_raises_plainly():
    with pytest.raises(TypeError, match="not_a_real_param"):
        Agent(name="a", instructions="x", not_a_real_param=1)
