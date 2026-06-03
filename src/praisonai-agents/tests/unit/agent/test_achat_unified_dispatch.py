"""Unit tests for unified achat dispatch (Issue #1703)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from praisonaiagents import Agent


def _fake_completion(content: str = "Mock async reply"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, reasoning_content=None))]
    )


@pytest.mark.asyncio
async def test_unified_achat_returns_after_single_dispatch():
    """achat must return after one unified dispatch, not loop forever."""
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")
    agent._using_custom_llm = False
    agent.self_reflect = False

    mock_unified = AsyncMock(return_value=_fake_completion())

    with patch.object(agent, "_execute_unified_achat_completion", mock_unified), patch.object(
        agent, "_apply_guardrail_with_retry", return_value="Mock async reply"
    ), patch.object(
        agent, "_atrigger_after_agent_hook", new_callable=AsyncMock, return_value="Mock async reply"
    ), patch.object(
        agent, "_execute_callback_and_display"
    ), patch.object(
        agent, "_build_messages", return_value=([{"role": "user", "content": "hi"}], "hi")
    ), patch.object(
        agent, "_persist_message"
    ), patch.object(
        agent, "_format_tools_for_completion", return_value=[]
    ):
        result = await asyncio.wait_for(agent.achat("hi", stream=False), timeout=5)

    assert result == "Mock async reply"
    mock_unified.assert_called_once()


@pytest.mark.asyncio
async def test_unified_achat_completion_uses_execute_tool_async():
    """Async unified dispatch must wire execute_tool_async, not sync execute_tool."""
    agent = Agent(name="test", instructions="You are helpful", llm="gpt-4o-mini")
    agent._using_custom_llm = False

    mock_dispatcher = MagicMock()
    mock_dispatcher.achat_completion = AsyncMock(return_value=_fake_completion())
    agent._unified_dispatcher = mock_dispatcher

    with patch.object(agent, "_apply_guardrail_with_retry", return_value="ok"), patch.object(
        agent, "_atrigger_after_agent_hook", new_callable=AsyncMock, return_value="ok"
    ), patch.object(agent, "_execute_callback_and_display"), patch.object(
        agent, "_build_messages", return_value=([{"role": "user", "content": "hi"}], "hi")
    ), patch.object(agent, "_persist_message"), patch.object(
        agent, "_format_tools_for_completion", return_value=[]
    ):
        await agent._achat_impl(
            prompt="hi",
            temperature=1.0,
            tools=None,
            output_json=None,
            output_pydantic=None,
            reasoning_steps=False,
            stream=False,
            task_name=None,
            task_description=None,
            task_id=None,
            config=None,
            force_retrieval=False,
            skip_retrieval=True,
            attachments=None,
            _trace_emitter=MagicMock(),
        )

    call_kwargs = mock_dispatcher.achat_completion.call_args[1]
    tool_fn = call_kwargs.get("execute_tool_fn")
    assert tool_fn is not None
    assert getattr(tool_fn, "__name__", "") == "execute_tool_async"
