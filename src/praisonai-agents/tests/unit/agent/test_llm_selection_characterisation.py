"""T-05 step 1: pin how Agent.__init__ picks its LLM backend before the
~317-line selection block moves out of __init__.

Values recorded on main 849f1f6442. Each case checks what a caller can see:
whether the custom-LLM path is used, the backend's type, model and base URL,
and the retry / reasoning options forwarded to it.
"""
import types

import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.retry_utils import RetryBackoffConfig


class _OwnModel:
    def get_response(self, **kwargs):
        return "x"


CASES = [
    # name, kwargs, (custom, llm, backend type, model, base_url, max_retries kwarg, reasoning_effort kwarg)
    ("default", {}, (False, "gpt-4o-mini", "NoneType", None, None, None, None)),
    ("bare model", {"llm": "gpt-4o-mini"}, (False, "gpt-4o-mini", "NoneType", None, None, None, None)),
    ("model alias", {"model": "gpt-4o-mini"}, (False, "gpt-4o-mini", "NoneType", None, None, None, None)),
    ("provider/model", {"llm": "anthropic/claude-3-haiku"},
     (True, "anthropic/claude-3-haiku", "LLM", "anthropic/claude-3-haiku", None, None, None)),
    ("dict", {"llm": {"model": "openai/gpt-4o-mini", "temperature": 0.1}},
     (True, "openai/gpt-4o-mini", "LLM", "openai/gpt-4o-mini", None, None, None)),
    ("base_url", {"llm": "gpt-4o-mini", "base_url": "http://localhost:9/v1"},
     (True, "gpt-4o-mini", "LLM", "gpt-4o-mini", "http://localhost:9/v1", None, None)),
    ("retry False", {"llm": "openai/gpt-4o-mini", "retry": False},
     (True, "openai/gpt-4o-mini", "LLM", "openai/gpt-4o-mini", None, 0, None)),
    ("retry dict", {"llm": "openai/gpt-4o-mini", "retry": {"max_retries": 5}},
     (True, "openai/gpt-4o-mini", "LLM", "openai/gpt-4o-mini", None, 5, None)),
    ("retry config", {"llm": "openai/gpt-4o-mini", "retry": RetryBackoffConfig(max_retries=1)},
     (True, "openai/gpt-4o-mini", "LLM", "openai/gpt-4o-mini", None, 1, None)),
    ("reasoning", {"llm": "openai/gpt-4o-mini", "reasoning_effort": "low"},
     (True, "openai/gpt-4o-mini", "LLM", "openai/gpt-4o-mini", None, None, "low")),
]


def _seen(agent):
    inst = getattr(agent, "llm_instance", None)
    opts = agent._llm_option_kwargs
    return (agent._using_custom_llm, agent.llm, type(inst).__name__,
            getattr(inst, "model", None), getattr(inst, "base_url", None),
            opts.get("max_retries"), opts.get("reasoning_effort"))


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


@pytest.mark.parametrize("name,kwargs,expected", CASES, ids=[c[0] for c in CASES])
def test_backend_selection(name, kwargs, expected):
    assert _seen(Agent(name="a", instructions="hi", **kwargs)) == expected


@pytest.mark.parametrize("retry,expected", [(False, 0), ({"max_retries": 5}, 5), (None, 3)])
def test_retry_reaches_the_backend(retry, expected):
    kwargs = {"llm": "openai/gpt-4o-mini"}
    if retry is not None:
        kwargs["retry"] = retry
    agent = Agent(name="a", instructions="hi", **kwargs)
    assert agent.llm_instance._max_retries == expected


def test_own_model_object_is_adopted():
    own = _OwnModel()
    agent = Agent(name="a", instructions="hi", llm=own)
    assert agent._using_custom_llm is True
    assert agent.llm_instance is own


def test_local_descriptor_resolves_to_its_target(monkeypatch):
    import praisonaiagents.local as local

    target = types.SimpleNamespace(
        litellm_model="openai/llama3", base_url="http://127.0.0.1:1234",
        openai_base_url="http://127.0.0.1:1234/v1", api_key="local-key",
        engine=object(),  # not OLLAMA: the OpenAI-style /v1 URL is used
    )
    monkeypatch.setattr(local, "resolve", lambda spec=None: target)
    agent = Agent(name="a", instructions="hi", llm="local")
    assert agent._local_target is target
    assert agent.llm_instance.model == "openai/llama3"
    assert agent.llm_instance.base_url == "http://127.0.0.1:1234/v1"
