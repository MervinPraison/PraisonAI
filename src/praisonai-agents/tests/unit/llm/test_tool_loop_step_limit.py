"""Tool continuations must reach the configured step limit and finalizer."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from praisonaiagents.llm.llm import LLM

ModelResponse = pytest.importorskip("litellm").ModelResponse


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("tool_name", ["sequentialthinking", "ordinary_tool"])
@pytest.mark.parametrize("limit", [1, 3, 5])
async def test_repeated_tool_calls_finalize_at_step_limit(monkeypatch, asynchronous, tool_name, limit):
    llm = LLM(model="openai/gpt-4o-mini", api_key="test-key")
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: False)
    response = ModelResponse(choices=[{
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call-thinking",
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps({"nextThoughtNeeded": True}),
                },
            }],
        },
    }])
    monkeypatch.setattr(llm, "_completion_with_retry", Mock(return_value=response))
    monkeypatch.setattr(llm, "_acompletion_with_retry", AsyncMock(return_value=response))
    finalise = AsyncMock(return_value="Budget summary") if asynchronous else Mock(return_value="Budget summary")
    monkeypatch.setattr(llm, "_finalise_on_limit_async" if asynchronous else "_finalise_on_limit", finalise)
    calls = []

    def execute(name, arguments, **kwargs):
        calls.append((name, arguments))
        if len(calls) > limit:
            pytest.fail("Tool loop exceeded its configured step limit")
        return "More work remains"

    options = dict(
        prompt="Keep using the tool until the step budget is exhausted.",
        tools=[{
            "type": "function",
            "function": {
                "name": tool_name,
                "description": "Continue working",
                "parameters": {"type": "object", "properties": {"nextThoughtNeeded": {"type": "boolean"}}},
            },
        }],
        execute_tool_fn=execute,
        stream=False,
        verbose=False,
        max_iterations=limit,
    )
    result = await llm.get_response_async(**options) if asynchronous else llm.get_response(**options)

    assert len(calls) == limit
    assert result == "Budget summary"
    assert llm._last_stop_reason == "max_steps"
    if asynchronous:
        finalise.assert_awaited_once()
    else:
        finalise.assert_called_once()
