"""T-05 step 2a: pin how Agent.__init__ unpacks llm= / model= / LLMConfig
before that block moves out of __init__.

Values recorded on main 33d767a0ce. Each case checks what a caller can see:
the chosen model, base URL, API key, fallback models and failover manager,
plus the llm= deprecation warning and where it points.
"""
import warnings

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import LLMConfig
from praisonaiagents.utils import deprecation

CFG = dict(model="openai/gpt-4o-mini", base_url="http://cfg/v1", api_key="cfg-key",
           fallback_models=["openai/gpt-4o"])

CASES = [
    # name, kwargs, (llm, base_url, api_key, fallback_models)
    ("llm=LLMConfig", {"llm": LLMConfig(**CFG)},
     ("openai/gpt-4o-mini", "http://cfg/v1", "cfg-key", ["openai/gpt-4o"])),
    ("model=LLMConfig", {"model": LLMConfig(**CFG)},
     ("openai/gpt-4o-mini", "http://cfg/v1", "cfg-key", ["openai/gpt-4o"])),
    ("explicit kwargs beat llm=LLMConfig",
     {"llm": LLMConfig(**CFG), "base_url": "http://kw/v1", "api_key": "kw-key"},
     ("openai/gpt-4o-mini", "http://kw/v1", "kw-key", ["openai/gpt-4o"])),
    ("explicit kwargs beat model=LLMConfig",
     {"model": LLMConfig(**CFG), "base_url": "http://kw/v1", "api_key": "kw-key"},
     ("openai/gpt-4o-mini", "http://kw/v1", "kw-key", ["openai/gpt-4o"])),
    ("LLMConfig without optionals", {"model": LLMConfig(model="openai/gpt-4o-mini")},
     ("openai/gpt-4o-mini", None, None, [])),
    ("model string", {"model": "openai/gpt-4o-mini"},
     ("openai/gpt-4o-mini", None, None, [])),
    ("llm string", {"llm": "openai/gpt-4o-mini"},
     ("openai/gpt-4o-mini", None, None, [])),
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(deprecation, "_warned_params", set())


@pytest.mark.parametrize("name,kwargs,expected", CASES, ids=[c[0] for c in CASES])
def test_unpacking(name, kwargs, expected):
    agent = Agent(name="a", instructions="hi", **kwargs)
    assert (agent.llm, agent.base_url, agent.api_key, agent.fallback_models) == expected


def test_fallback_models_are_a_copy():
    cfg = LLMConfig(model="openai/gpt-4o-mini", fallback_models=["openai/gpt-4o"])
    agent = Agent(name="a", instructions="hi", model=cfg)
    cfg.fallback_models.append("x")
    assert agent.fallback_models == ["openai/gpt-4o"]


def test_llm_and_model_together_are_refused():
    with pytest.raises(TypeError):
        Agent(name="a", instructions="hi", llm="openai/gpt-4o-mini", model="openai/gpt-4o")


def test_llm_string_warns_once_at_the_callers_line():
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        Agent(name="a", instructions="hi", llm="openai/gpt-4o-mini")
        Agent(name="b", instructions="hi", llm="openai/gpt-4o-mini")
    dep = [w for w in seen if issubclass(w.category, DeprecationWarning)
           and "Parameter 'llm'" in str(w.message)]
    assert len(dep) == 1
    assert dep[0].filename == __file__


@pytest.mark.parametrize("kwargs", [{"llm": LLMConfig(**CFG)}, {"model": LLMConfig(**CFG)},
                                    {"model": "openai/gpt-4o-mini"}])
def test_no_llm_warning_for_llmconfig_or_model(kwargs):
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        Agent(name="a", instructions="hi", **kwargs)
    assert not [w for w in seen if "Parameter 'llm'" in str(w.message)]


@pytest.mark.parametrize("key", ["llm", "model"])
def test_auth_profiles_build_a_failover_manager(key):
    cfg = LLMConfig(model="openai/gpt-4o-mini",
                    auth_profiles=[{"provider": "openai", "api_key": "sk-one"}])
    agent = Agent(name="a", instructions="hi", **{key: cfg})
    assert agent._failover_manager is not None
    assert agent._using_custom_llm is True
