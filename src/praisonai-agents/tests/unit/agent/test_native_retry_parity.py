"""Native OpenAI-client path retries transient errors by default.

Verifies parity with the LiteLLM path: a default ``Agent`` retries a retryable
``LLMError`` (e.g. 429) and succeeds, fires ``ON_RETRY`` once, and re-raises
non-retryable errors immediately.
"""

import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.retry_utils import RetryBackoffConfig
from praisonaiagents.errors import LLMError
from praisonaiagents.hooks import HookEvent


def _fast_retry_agent():
    # Tiny delays keep the test fast while still exercising the retry loop.
    return Agent(
        name="test",
        instructions="Be helpful",
        retry=RetryBackoffConfig(base_delay=0.001, max_delay=0.002, max_retries=3),
    )


def test_native_path_retries_retryable_error_then_succeeds():
    agent = _fast_retry_agent()

    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMError("rate limited", is_retryable=True)
        return "ok"

    agent._execute_unified_chat_completion = flaky

    retries = []
    original = agent._hook_runner.execute_sync

    def spy(event, input_data, target=None):
        if event == HookEvent.ON_RETRY:
            retries.append(input_data)
        return original(event, input_data, target)

    agent._hook_runner.execute_sync = spy

    result = agent._chat_completion_with_retry([{"role": "user", "content": "hi"}])

    assert result == "ok"
    assert calls["n"] == 2
    assert len(retries) == 1


def test_native_path_reraises_non_retryable_immediately():
    agent = _fast_retry_agent()

    calls = {"n": 0}

    def fatal(*args, **kwargs):
        calls["n"] += 1
        raise LLMError("bad request", is_retryable=False)

    agent._execute_unified_chat_completion = fatal

    with pytest.raises(LLMError):
        agent._chat_completion_with_retry([{"role": "user", "content": "hi"}])

    assert calls["n"] == 1


def test_retry_false_skips_native_retry_loop():
    agent = Agent(name="test", instructions="Be helpful", retry=False)

    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        raise LLMError("rate limited", is_retryable=True)

    agent._execute_unified_chat_completion = flaky

    with pytest.raises(LLMError):
        agent._chat_completion_with_retry([{"role": "user", "content": "hi"}])

    assert calls["n"] == 1
