"""A post-tool follow-up that asks for another tool is a new round, not the answer (F-06)."""

import json
from unittest.mock import AsyncMock

import pytest

from praisonaiagents.llm.llm import LLM

ModelResponse = pytest.importorskip("litellm").ModelResponse
ModelResponseStream = pytest.importorskip("litellm.types.utils").ModelResponseStream


def _message(content, call_id=None):
    message = {"role": "assistant", "content": content}
    if call_id:
        message["tool_calls"] = [{
            "index": 0, "id": call_id, "type": "function",
            "function": {"name": "lookup", "arguments": json.dumps({"q": call_id})},
        }]
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize("stream,verbose", [(False, False), (True, True)], ids=["plain", "verbose_stream"])
async def test_followup_with_new_tool_call_runs_another_round(monkeypatch, stream, verbose):
    llm = LLM(model="openai/gpt-4o-mini", api_key="test-key")
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: False)
    monkeypatch.setattr(llm, "_supports_streaming_tools", lambda: True)

    async def chunks(message):
        yield ModelResponseStream(choices=[{"delta": message}])

    def complete(**kwargs):
        done = sum(1 for m in kwargs.get("messages", []) if m.get("role") == "tool")
        message = [_message("", "call-1"), _message("Let me check again", "call-2"), _message("done")][min(done, 2)]
        if kwargs.get("stream"):
            return chunks(message)
        return ModelResponse(choices=[{"finish_reason": "tool_calls" if done < 2 else "stop", "message": message}])

    monkeypatch.setattr(llm, "_acompletion_with_retry", AsyncMock(side_effect=complete))
    calls = []

    def execute(name, arguments, **kwargs):
        calls.append(arguments)
        return "found"

    result = await llm.get_response_async(
        prompt="Look it up twice.",
        tools=[{"type": "function", "function": {
            "name": "lookup", "description": "Look up.",
            "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
        }}],
        execute_tool_fn=execute,
        stream=stream,
        verbose=verbose,
    )

    assert result == "done"
    assert [c["q"] for c in calls] == ["call-1", "call-2"]
