"""Auto-continuation of answers cut off by the output-token limit (#5810)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from praisonaiagents.llm._continuation import CONTINUE_PROMPT, OutputContinuation


def _resp(content, finish_reason):
    return {
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def test_take_and_stitch():
    c = OutputContinuation(True)
    msgs = []
    assert c.take(msgs, "Hello ", True)
    assert msgs[-1] == {"role": "user", "content": CONTINUE_PROMPT}
    assert msgs[-2] == {"role": "assistant", "content": "Hello "}
    assert c.stitch("world") == "Hello world"


def test_not_truncated_or_disabled_is_noop():
    msgs = []
    assert not OutputContinuation(True).take(msgs, "done", False)
    assert not OutputContinuation(False).take(msgs, "part", True)
    assert not OutputContinuation(0).take(msgs, "part", True)
    assert not OutputContinuation(True).take(msgs, "", True)
    assert msgs == []
    assert OutputContinuation(True).stitch("x") == "x"


def test_cap_bounds_continuations():
    c = OutputContinuation(2)
    msgs = []
    assert c.take(msgs, "a", True) and c.take(msgs, "b", True)
    assert not c.take(msgs, "c", True)


def _llm():
    from praisonaiagents.llm.llm import LLM
    llm = LLM(model="groq/llama-3.1-8b-instant")
    return llm


def _run_sync(responses, **kw):
    llm = _llm()
    seen = []

    def fake(**params):
        seen.append(list(params["messages"]))
        return responses.pop(0)

    with patch.object(type(llm), "_supports_responses_api", return_value=False), \
            patch.object(llm, "_completion_with_retry", side_effect=fake):
        out = llm.get_response("write", stream=False, verbose=False, **kw)
    return llm, out, seen


def test_litellm_sync_continues_and_stitches():
    llm, out, seen = _run_sync([_resp("Hello ", "length"), _resp("world.", "stop")])
    assert out == "Hello world."
    assert llm._last_stop_reason == "completed"
    assert seen[1][-1]["content"] == CONTINUE_PROMPT
    assert seen[1][-2] == {"role": "assistant", "content": "Hello "}


def test_litellm_sync_cap_surfaces_truncated():
    llm, out, seen = _run_sync(
        [_resp("a", "length"), _resp("b", "length")], output_continuation=1
    )
    assert out == "ab"
    assert llm._last_stop_reason == "length_truncated"
    assert len(seen) == 2


def test_litellm_sync_opt_out_keeps_old_behaviour():
    llm, out, seen = _run_sync([_resp("a", "length")], output_continuation=False)
    assert out == "a"
    assert llm._last_stop_reason == "length_truncated"
    assert len(seen) == 1


def test_litellm_async_continues_and_stitches():
    llm = _llm()
    responses = [_resp("Hello ", "length"), _resp("world.", "stop")]

    async def fake(**params):
        from litellm import ModelResponse
        return ModelResponse(**responses.pop(0))

    with patch.object(type(llm), "_supports_responses_api", return_value=False), \
            patch.object(llm, "_acompletion_with_retry", side_effect=fake):
        out = asyncio.run(llm.get_response_async("write", stream=False, verbose=False))
    assert out == "Hello world."
    assert llm._last_stop_reason == "completed"


def _completion(content, finish_reason):
    from openai.types.chat import ChatCompletion
    return ChatCompletion.model_validate({
        "id": "x", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
        "choices": [{"index": 0, "finish_reason": finish_reason,
                     "message": {"role": "assistant", "content": content}}],
    })


def _run_openai(responses, **kw):
    from praisonaiagents.llm.openai_client import OpenAIClient
    client = OpenAIClient(api_key="sk-test")
    seen = []

    async def fake(messages, **params):
        seen.append(list(messages))
        return responses.pop(0)

    with patch.object(client, "acreate_completion", side_effect=fake):
        resp = asyncio.run(client.achat_completion_with_tools(
            [{"role": "user", "content": "write"}], stream=False, **kw))
    return client, resp, seen


def test_openai_native_continues_and_stitches():
    client, resp, seen = _run_openai([_completion("Hello ", "length"), _completion("world.", "stop")])
    assert resp.choices[0].message.content == "Hello world."
    assert client._last_stop_reason == "completed"
    assert seen[1][-1]["content"] == CONTINUE_PROMPT


def test_openai_native_cap_surfaces_truncated():
    client, resp, seen = _run_openai(
        [_completion("a", "length"), _completion("b", "length")], output_continuation=1
    )
    assert resp.choices[0].message.content == "ab"
    assert client._last_stop_reason == "length_truncated"
    assert len(seen) == 2


def test_execution_config_round_trip():
    from praisonaiagents.config.feature_configs import ExecutionConfig
    assert ExecutionConfig().output_continuation is True
    cfg = ExecutionConfig.from_dict(ExecutionConfig(output_continuation=False).to_dict())
    assert cfg.output_continuation is False


def test_litellm_structured_output_is_not_continued():
    from pydantic import BaseModel

    class Out(BaseModel):
        text: str

    _, _, seen = _run_sync([_resp('{"text": "a', "length")], output_json=Out)
    assert len(seen) == 1


def _chunk(content, finish_reason=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=None), finish_reason=finish_reason)])


def test_litellm_streamed_length_is_continued():
    llm = _llm()
    streams = [[_chunk("Hello "), _chunk(None, "length")], [_chunk("world."), _chunk(None, "stop")]]
    seen = []

    def fake(**params):
        seen.append(list(params["messages"]))
        return iter(streams.pop(0))

    with patch.object(type(llm), "_supports_responses_api", return_value=False), \
            patch.object(llm, "_completion_with_retry", side_effect=fake):
        out = llm.get_response("write", stream=True, verbose=False)
    assert out == "Hello world."
    assert len(seen) == 2
    assert llm._last_stop_reason == "completed"


def test_openai_native_structured_output_is_not_continued():
    _, resp, seen = _run_openai(
        [_completion('{"a": ', "length")], response_format={"type": "json_object"}
    )
    assert len(seen) == 1
    assert resp.choices[0].message.content == '{"a": '


def test_openai_native_cancel_keeps_earlier_pieces():
    cancelled = SimpleNamespace(flag=False)
    token = SimpleNamespace(is_set=lambda: cancelled.flag)
    responses = [_completion("a", "length"), _completion("b", "length")]

    def nxt():
        if len(responses) == 1:
            cancelled.flag = True
        return responses.pop(0)

    from praisonaiagents.llm.openai_client import OpenAIClient
    client = OpenAIClient(api_key="sk-test")

    async def fake(messages, **params):
        return nxt()

    with patch.object(client, "acreate_completion", side_effect=fake):
        resp = asyncio.run(client.achat_completion_with_tools(
            [{"role": "user", "content": "write"}], stream=False, cancel_token=token))
    assert resp.choices[0].message.content == "ab"
    assert client._last_stop_reason == "cancelled"


def _tool_resp(finish_reason):
    return {
        "choices": [{"finish_reason": finish_reason, "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "add", "arguments": '{"a": 1, "b": 2}'}}]}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def test_truncated_tool_call_does_not_continue_finished_answer():
    llm, out, seen = _run_sync(
        [_tool_resp("length"), _resp("Done: 3.", "stop")],
        tools=[_add], execute_tool_fn=lambda name, args, *a, **k: _add(**args),
    )
    assert out == "Done: 3."
    assert len(seen) == 2
    assert all(m.get("content") != CONTINUE_PROMPT for m in seen[-1])


def test_text_response_format_still_continues():
    _, resp, seen = _run_openai(
        [_completion("Hello ", "length"), _completion("world.", "stop")],
        response_format={"type": "text"},
    )
    assert resp.choices[0].message.content == "Hello world."
    assert len(seen) == 2
