"""T-05 step 2b: pin the LLM option kwargs Agent.__init__ builds (retry= and
reasoning_effort= folded into the kwargs every LLM construction forwards)
before that block moves out of __init__. Values recorded on main 33d767a0ce.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.retry_utils import RetryBackoffConfig

BASE = {"metrics": False, "max_iter": 20, "web_search": None, "web_fetch": None,
        "prompt_caching": None, "claude_memory": None}

CASES = [
    ("default", {}, {}),
    ("retry False", {"retry": False}, {"max_retries": 0}),
    ("retry True", {"retry": True}, {}),
    ("retry dict", {"retry": {"max_retries": 5}}, {"max_retries": 5}),
    ("retry config", {"retry": RetryBackoffConfig(max_retries=1)}, {"max_retries": 1}),
    ("reasoning", {"reasoning_effort": "low"}, {"reasoning_effort": "low"}),
    ("both", {"retry": False, "reasoning_effort": "high"}, {"max_retries": 0, "reasoning_effort": "high"}),
]


@pytest.mark.parametrize("name,kwargs,extra", CASES, ids=[c[0] for c in CASES])
def test_option_kwargs(name, kwargs, extra, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    agent = Agent(name="a", instructions="hi", model="openai/gpt-4o-mini", **kwargs)
    assert agent._llm_option_kwargs == {**BASE, **extra}


def test_bad_retry_dict_still_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(TypeError):
        Agent(name="a", instructions="hi", model="openai/gpt-4o-mini", retry={"nope": 1})
