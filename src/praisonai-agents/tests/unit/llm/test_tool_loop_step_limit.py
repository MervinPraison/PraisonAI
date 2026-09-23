"""Tool continuations must reach the configured step limit and finalizer."""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel

from praisonaiagents.llm.llm import LLM

ModelResponse = pytest.importorskip("litellm").ModelResponse
ModelResponseStream = pytest.importorskip("litellm.types.utils").ModelResponseStream


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("tool_name", ["sequentialthinking", "ordinary_tool"])
@pytest.mark.parametrize("limit", [1, 3, 5])
async def test_repeated_tool_calls_finalize_at_step_limit(monkeypatch, asynchronous, tool_name, limit):
    await _assert_step_limit(monkeypatch, asynchronous, tool_name, limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("output_mode", ["output_json", "output_pydantic", "self_reflect"])
async def test_async_output_modes_preserve_budget_summary(monkeypatch, output_mode):
    await _assert_step_limit(monkeypatch, True, "ordinary_tool", 3, output_mode)


async def _assert_step_limit(monkeypatch, asynchronous, tool_name, limit, output_mode="plain"):
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
    final_answer = '{"summary": "Budget summary"}'
    reflection_answers = []

    async def chunks(message):
        yield ModelResponseStream(choices=[{"delta": message}])

    def complete(**kwargs):
        messages = kwargs.get("messages", [])
        if output_mode == "self_reflect" and "satisfactory" in messages[-1]["content"]:
            reflection_answers.append(messages[-2]["content"])
            return chunks({"content": '{"reflection": "Done", "satisfactory": "yes"}'})
        if kwargs.get("stream"):
            message = response.choices[0].message.model_dump()
            message["tool_calls"][0]["index"] = 0
            return chunks(message)
        return response

    monkeypatch.setattr(llm, "_completion_with_retry", Mock(side_effect=complete))
    monkeypatch.setattr(llm, "_acompletion_with_retry", AsyncMock(side_effect=complete))
    finalise = AsyncMock(return_value=final_answer) if asynchronous else Mock(return_value=final_answer)
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
    if output_mode in ("output_json", "output_pydantic"):
        class Answer(BaseModel):
            summary: str

        options[output_mode] = Answer
    elif output_mode == "self_reflect":
        options.update(self_reflect=True, stream=True, min_reflect=1, max_reflect=1)
    result = await llm.get_response_async(**options) if asynchronous else llm.get_response(**options)

    assert len(calls) == limit
    assert result == final_answer
    assert llm._last_stop_reason == "max_steps"
    if asynchronous:
        finalise.assert_awaited_once()
    else:
        finalise.assert_called_once()
    if output_mode == "self_reflect":
        assert reflection_answers == [final_answer]
    elif output_mode in ("output_json", "output_pydantic"):
        assert llm.chat_history[-1]["content"] == final_answer
