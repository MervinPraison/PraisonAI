"""Sync self-reflection must stop retrying an unparseable reflection.

The async handler bounds the retry with `if reflection_count >= self.max_reflect`.
The sync handler increments the counter and `continue`s unconditionally, so a
reflection that never parses -- the realistic trigger is an OpenAI
structured-output refusal, where `message.parsed` is None and reading
`.reflection` off it raises AttributeError -- loops forever at two LLM calls a
turn.  `chat()` never returns.
"""
import asyncio
import types

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import ReflectionConfig
from praisonaiagents.llm.openai_client import OpenAIClient

CAP = 40  # generous: a bounded loop uses <10


class _CallCap(BaseException):
    """BaseException so the agent's own `except Exception` cannot swallow it."""


class _Msg:
    role = "assistant"
    refusal = None
    parsed = None
    content = None
    tool_calls = None

    def __init__(self, content=None):
        self.content = content

    def model_dump(self):
        return {"role": "assistant", "content": self.content}


class _Refusal(_Msg):
    """Structured-output refusal: `parsed` is None, so `.reflection` raises."""

    def __init__(self):
        super().__init__(content=None)
        self.refusal = "I cannot comply."


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15
    completion_tokens_details = None
    prompt_tokens_details = None

    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class _Resp:
    id = "chatcmpl-test"
    created = 0
    object = "chat.completion"
    model = "gpt-4o-mini"

    def __init__(self, msg):
        self.choices = [types.SimpleNamespace(message=msg, finish_reason="stop",
                                              index=0, delta=None)]
        self.usage = _Usage()


class _Transport:
    """Answers `create` with text and `parse` with a refusal, counting both."""

    def __init__(self):
        self.n = 0

    def _tick(self):
        self.n += 1
        if self.n > CAP:
            raise _CallCap(f"exceeded {CAP} LLM calls -- loop is unbounded")

    def create(self, **kwargs):
        self._tick()
        return _Resp(_Msg(content=f"A{self.n}"))

    async def acreate(self, **kwargs):
        return self.create(**kwargs)

    def parse(self, **kwargs):
        self._tick()
        return _Resp(_Refusal())

    async def aparse(self, **kwargs):
        return self.parse(**kwargs)


def _agent():
    t = _Transport()
    agent = Agent(name="A", instructions="x", llm="gpt-4o-mini",
                  reflection=ReflectionConfig(min_iterations=1, max_iterations=3))

    sync_c = types.SimpleNamespace(name="create", create=t.create)
    sync_p = types.SimpleNamespace(parse=t.parse)
    async_c = types.SimpleNamespace(create=t.acreate)
    async_p = types.SimpleNamespace(parse=t.aparse)

    client = OpenAIClient(api_key="sk-not-a-real-key")
    client._sync_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=sync_c),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(completions=sync_p)),
        responses=None)
    client._async_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=async_c),
        beta=types.SimpleNamespace(chat=types.SimpleNamespace(completions=async_p)),
        responses=None)
    agent._Agent__openai_client = client
    agent._unified_dispatcher = None
    return agent, t


def test_sync_reflection_terminates_when_the_reflection_never_parses():
    agent, t = _agent()
    try:
        result = agent.chat("q")
    except _CallCap as exc:
        pytest.fail(str(exc))
    assert result, "bounded loop must still return the un-reflected answer"


def test_sync_reflection_call_count_is_bounded_like_async():
    agent, t = _agent()
    try:
        agent.chat("q")
    except _CallCap as exc:
        pytest.fail(str(exc))
    sync_calls = t.n

    agent, t = _agent()
    asyncio.run(agent.achat("q"))
    async_calls = t.n

    # The sync path costs more per reflection round (a separate defect), but it
    # must at least stay within a small constant of the async bound.
    assert sync_calls <= async_calls * 3, (
        f"sync used {sync_calls} LLM calls vs async {async_calls}")
