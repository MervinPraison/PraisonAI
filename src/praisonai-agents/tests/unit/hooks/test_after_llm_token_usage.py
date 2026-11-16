"""AFTER_LLM reports the usage counted by the existing completion path."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from openai.types.chat import ChatCompletion
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import HooksConfig
from praisonaiagents.hooks import HookEvent, HookRegistry, HookResult


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("with_usage", [False, True])
def test_after_llm_receives_current_completion_usage(asynchronous, with_usage):
    usage = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
    completion = ChatCompletion(
        id="chatcmpl-fixture", created=1, object="chat.completion",
        model="gpt-4o-mini",
        choices=[{
            "index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": "Fixture greeting."},
        }],
        usage=usage if with_usage else None,
    )
    observed = []
    registry = HookRegistry()

    def after_llm(event):
        observed.append(event.tokens_used)
        return HookResult.allow()

    registry.register_function(HookEvent.AFTER_LLM, after_llm)
    agent = Agent(
        name="usage-fixture", instructions="Greet.", model="gpt-4o-mini",
        api_key="synthetic-offline-fixture",
        hooks=HooksConfig(registry=registry),
        output={"verbose": False, "stream": False},
        reflection=False, memory=False, rules=False, retry=False,
    )
    agent._unified_dispatcher = SimpleNamespace(
        chat_completion=Mock(return_value=completion),
        achat_completion=AsyncMock(return_value=completion),
    )
    if asynchronous:
        result = asyncio.run(agent.achat("Hello", stream=False))
        agent._unified_dispatcher.achat_completion.assert_awaited_once()
    else:
        result = agent.chat("Hello", stream=False)
        agent._unified_dispatcher.chat_completion.assert_called_once()
    assert result == "Fixture greeting."
    assert observed == [18 if with_usage else 0]
