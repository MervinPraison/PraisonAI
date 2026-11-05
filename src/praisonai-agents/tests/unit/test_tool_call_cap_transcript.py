"""Regression test for #6202: capping a tool batch must not leave orphaned tool_calls."""
import asyncio
import json

import pytest

pytest.importorskip("litellm")


def _litellm():
    # Resolve at test time: other tests may reload/replace ``litellm`` in
    # sys.modules after collection, and llm.py imports it lazily per call.
    import litellm
    return litellm


def ModelResponse(**kw):  # noqa: N802
    return _litellm().ModelResponse(**kw)


def _tc(i):
    return {"id": f"c{i}", "type": "function",
            "function": {"name": "ping", "arguments": json.dumps({"n": i})}}


def _ping(n: int) -> str:
    "ping"
    return f"pong{n}"


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_truncated_batch_has_no_orphaned_tool_calls(monkeypatch, mode):
    sent = []

    def _respond(kwargs):
        sent.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        if len(sent) == 1:
            return ModelResponse(choices=[{"message": {"role": "assistant", "content": "",
                                                       "tool_calls": [_tc(i) for i in range(12)]},
                                           "finish_reason": "tool_calls", "index": 0}])
        return ModelResponse(choices=[{"message": {"role": "assistant", "content": "done"},
                                       "finish_reason": "stop", "index": 0}])

    async def _afake(*a, **k):
        return _respond(k)

    monkeypatch.setattr(_litellm(), "completion", lambda *a, **k: _respond(k))
    monkeypatch.setattr(_litellm(), "acompletion", _afake)

    from praisonaiagents import Agent
    agent = Agent(instructions="x", model="anthropic/claude-3-haiku-20240307",
                  tools=[_ping], output="silent")
    result = agent.start("go") if mode == "sync" else asyncio.run(agent.astart("go"))

    assert result == "done"
    follow_up = sent[1]
    declared = [t["id"] for m in follow_up if m.get("tool_calls") for t in m["tool_calls"]]
    replied = [m["tool_call_id"] for m in follow_up if m.get("role") == "tool"]
    assert sorted(declared) == sorted(replied)
    assert len(declared) == 10  # default max_tool_calls_per_turn


def test_stream_fallback_keeps_text_sent_with_capped_tool_calls(monkeypatch):
    """Text returned alongside tool calls must still be yielded once the cap is hit."""
    sent = []

    def _respond(*a, **k):
        sent.append(k)
        n = len(sent)
        if n <= 2:
            return ModelResponse(choices=[{"message": {"role": "assistant", "content": f"text{n}",
                                                       "tool_calls": [_tc(n)]},
                                           "finish_reason": "tool_calls", "index": 0}])
        return ModelResponse(choices=[{"message": {"role": "assistant", "content": "final"},
                                       "finish_reason": "stop", "index": 0}])

    monkeypatch.setattr(_litellm(), "completion", _respond)

    from praisonaiagents.llm.llm import LLM
    llm = LLM(model="anthropic/claude-3-haiku-20240307")
    monkeypatch.setattr(llm, "_supports_streaming_tools", lambda: False)
    chunks = list(llm.get_response_stream(
        "go", tools=[_ping], execute_tool_fn=lambda name, args: _ping(**args),
        max_tool_calls_per_turn=1))

    assert "text1" in chunks and "text2" in chunks  # text2 arrived at the cap
