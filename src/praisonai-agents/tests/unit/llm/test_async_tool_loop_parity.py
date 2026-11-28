"""Gap 1 of #6735: the async litellm tool loop must match the sync loop.

A two-tool chain must produce the same llm_calls, tools_ran and result for
chat and achat, with stream set to False and to True.
"""

import pytest

from praisonaiagents import Agent

ModelResponse = pytest.importorskip("litellm").ModelResponse
ModelResponseStream = pytest.importorskip("litellm.types.utils").ModelResponseStream


def _tool_call(name, call_id):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


def _reply(messages, tools):
    if not tools:
        return "answered WITHOUT tools offered", []
    # Tool result messages may not carry a function name, so count them.
    done = sum(1 for m in messages if m.get("role") == "tool")
    if done < 1:
        return "", [_tool_call("step_a", "call_a")]
    if done < 2:
        return "", [_tool_call("step_b", "call_b")]
    return "final: did A and B", []


def _make_response(content, tool_calls):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return ModelResponse(
        choices=[{
            "index": 0,
            "message": message,
            "finish_reason": "tool_calls" if tool_calls else "stop",
        }]
    )


def _make_stream(content, tool_calls):
    delta = {"role": "assistant", "content": content}
    if tool_calls:
        delta["tool_calls"] = [
            {
                "index": i,
                "id": tc["id"],
                "type": "function",
                "function": tc["function"],
            }
            for i, tc in enumerate(tool_calls)
        ]
    return iter([
        ModelResponseStream(
            choices=[{"index": 0, "delta": delta, "finish_reason": None}]
        )
    ])


def _make_async_stream(content, tool_calls):
    async def _gen():
        for chunk in _make_stream(content, tool_calls):
            yield chunk
    return _gen()


def _install(monkeypatch, agent, recorder):
    llm = agent.llm_instance
    monkeypatch.setattr(llm, "_supports_responses_api", lambda: False)
    monkeypatch.setattr(llm, "_supports_streaming_tools", lambda: True)
    # anthropic/claude-x uses AnthropicAdapter, which disables streaming
    # even when _supports_streaming_tools is patched.
    if getattr(llm, "_provider_adapter", None) is not None:
        monkeypatch.setattr(llm._provider_adapter, "supports_streaming", lambda: True)

    def _completion_with_retry(**kwargs):
        recorder["calls"] += 1
        recorder["streams"].append(bool(kwargs.get("stream")))
        content, tool_calls = _reply(kwargs.get("messages", []), kwargs.get("tools"))
        if kwargs.get("stream"):
            return _make_stream(content, tool_calls)
        return _make_response(content, tool_calls)

    async def _acompletion_with_retry(**kwargs):
        recorder["calls"] += 1
        recorder["streams"].append(bool(kwargs.get("stream")))
        content, tool_calls = _reply(kwargs.get("messages", []), kwargs.get("tools"))
        if kwargs.get("stream"):
            return _make_async_stream(content, tool_calls)
        return _make_response(content, tool_calls)

    monkeypatch.setattr(llm, "_completion_with_retry", _completion_with_retry)
    monkeypatch.setattr(llm, "_acompletion_with_retry", _acompletion_with_retry)


def _collect(result):
    if result is None or isinstance(result, str):
        return result
    return "".join(str(c) for c in result)


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True], ids=["no_stream", "stream"])
async def test_chat_and_achat_two_tool_chain_parity(monkeypatch, tmp_path, stream):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    tools_ran = []

    def step_a():
        """Run step A."""
        tools_ran.append("a")
        return "A done"

    def step_b():
        """Run step B."""
        tools_ran.append("b")
        return "B done"

    sync_recorder = {"calls": 0, "streams": []}
    sync_agent = Agent(
        name="w",
        llm="anthropic/claude-x",
        tools=[step_a, step_b],
        output="silent",
        api_key="test-key",
    )
    _install(monkeypatch, sync_agent, sync_recorder)
    sync_result = _collect(sync_agent.chat("do A then B", stream=stream))
    sync_tools = list(tools_ran)

    tools_ran.clear()
    async_recorder = {"calls": 0, "streams": []}
    async_agent = Agent(
        name="w",
        llm="anthropic/claude-x",
        tools=[step_a, step_b],
        output="silent",
        api_key="test-key",
    )
    _install(monkeypatch, async_agent, async_recorder)
    async_result = _collect(await async_agent.achat("do A then B", stream=stream))
    async_tools = list(tools_ran)

    assert sync_recorder["calls"] == async_recorder["calls"]
    assert sync_tools == async_tools
    assert sync_result == async_result
    assert async_recorder["calls"] == 3
    assert async_tools == ["a", "b"]
    assert async_result == "final: did A and B"
    if stream:
        assert sync_recorder["streams"] and all(sync_recorder["streams"])
        assert async_recorder["streams"] and all(async_recorder["streams"])
    else:
        assert sync_recorder["streams"] and not any(sync_recorder["streams"])
        assert async_recorder["streams"] and not any(async_recorder["streams"])
