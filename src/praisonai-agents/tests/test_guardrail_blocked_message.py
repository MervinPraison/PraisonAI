"""Regression tests for issue #5596.

A guardrail that blocks model output must never make Agent.chat/achat return
``None`` (callers expect a ``str`` and crash on ``.strip()``). On a block the
agent returns a safe, non-empty fallback string instead of leaking the rejected
text.
"""

from unittest.mock import MagicMock

import pytest

from praisonaiagents import Agent, TaskOutput


def _blocking_guardrail(task_output: TaskOutput):
    """Reject every output, mimicking a forbidden-token guardrail."""
    return False, "contains forbidden token"


def test_guardrail_blocked_message_is_safe_non_empty_string():
    agent = Agent(
        name="GuardAgent",
        instructions="You are a test agent",
        llm="gpt-4o-mini",
        guardrails=_blocking_guardrail,
    )
    message = agent._guardrail_blocked_message("contains forbidden token")
    assert isinstance(message, str)
    assert message.strip()
    # Fixed safe string (FR-001): the guardrail reason must NOT leak to the
    # caller, since an LLM validator's reason can echo the rejected output.
    assert "contains forbidden token" not in message


def test_guardrail_blocked_message_without_reason():
    agent = Agent(
        name="GuardAgent",
        instructions="You are a test agent",
        llm="gpt-4o-mini",
        guardrails=_blocking_guardrail,
    )
    message = agent._guardrail_blocked_message()
    assert isinstance(message, str)
    assert message.strip()


def test_chat_returns_safe_message_not_none_on_block():
    agent = Agent(
        name="GuardAgent",
        instructions="You are a test agent",
        llm="gpt-4o-mini",
        guardrails=_blocking_guardrail,
    )
    # retries=0 so the retry loop raises immediately without a network call.
    agent.max_guardrail_retries = 0
    # Force the custom-LLM branch and feed it forbidden output offline.
    agent._using_custom_llm = True
    agent.llm_instance = MagicMock()
    agent.llm_instance.get_response.return_value = "LEAKME secret"

    result = agent.chat("say something")

    assert result is not None
    assert isinstance(result, str)
    assert result.strip()
    assert "LEAKME" not in result


@pytest.mark.asyncio
async def test_achat_returns_safe_message_not_none_on_block():
    agent = Agent(
        name="GuardAgent",
        instructions="You are a test agent",
        llm="gpt-4o-mini",
        guardrails=_blocking_guardrail,
    )
    agent.max_guardrail_retries = 0

    async def _fake_get_response_async(**kwargs):
        return "LEAKME secret"

    agent._using_custom_llm = True
    agent.llm_instance = MagicMock()
    agent.llm_instance.get_response_async = _fake_get_response_async

    result = await agent.achat("say something")

    assert result is not None
    assert isinstance(result, str)
    assert result.strip()
    assert "LEAKME" not in result


def test_chat_does_not_leak_guardrail_reason():
    """The fixed fallback must not echo the guardrail's rejection reason.

    An LLM validator's reason can quote the blocked output, so the reason is
    logged (and exposed via ``last_guardrail_error``) but never returned.
    """
    agent = Agent(
        name="GuardAgent",
        instructions="You are a test agent",
        llm="gpt-4o-mini",
        guardrails=_blocking_guardrail,
    )
    agent.max_guardrail_retries = 0
    agent._using_custom_llm = True
    agent.llm_instance = MagicMock()
    agent.llm_instance.get_response.return_value = "LEAKME secret"

    result = agent.chat("say something")

    assert isinstance(result, str) and result.strip()
    assert "LEAKME" not in result
    assert "contains forbidden token" not in result


def test_chat_returns_safe_message_with_reflection_enabled():
    """A guardrail block with self-reflection on still yields a safe string."""
    from praisonaiagents import ReflectionConfig

    agent = Agent(
        name="GuardAgent",
        instructions="You are a test agent",
        llm="gpt-4o-mini",
        guardrails=_blocking_guardrail,
        reflection=ReflectionConfig(min_iterations=1, max_iterations=1),
    )
    agent.max_guardrail_retries = 0
    agent._using_custom_llm = True
    agent.llm_instance = MagicMock()
    agent.llm_instance.get_response.return_value = "LEAKME secret"

    result = agent.chat("say something")

    assert result is not None
    assert isinstance(result, str)
    assert result.strip()
    assert "LEAKME" not in result
