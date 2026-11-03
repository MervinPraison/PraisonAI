"""Regression test for #6202: capping a tool batch must not leave orphaned tool_calls."""
import asyncio
import json

import pytest

litellm = pytest.importorskip("litellm")
from litellm import ModelResponse  # noqa: E402


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

    monkeypatch.setattr(litellm, "completion", lambda *a, **k: _respond(k))
    monkeypatch.setattr(litellm, "acompletion", _afake)

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
