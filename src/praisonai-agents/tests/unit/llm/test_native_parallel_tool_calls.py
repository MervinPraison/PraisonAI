"""
ExecutionConfig.parallel_tool_calls on the native OpenAI client tool loop
(openai_client.achat_completion_with_tools), issue #6338.

The model call is mocked; a threading.Barrier proves the batch really runs
concurrently (a sequential run would break the barrier).
"""

import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from praisonaiagents.llm.openai_client import OpenAIClient


def _call(idx, name="slow", args=None):
    return SimpleNamespace(
        id=f"call_{idx}",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(args or {"i": idx})),
    )


def _response(tool_calls):
    message = SimpleNamespace(content="", tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="tool_calls" if tool_calls else "stop")],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _client(monkeypatch, batch, seen_kwargs):
    c = OpenAIClient(api_key="test-key")
    responses = [_response(batch), _response(None)]

    def fake_stream(*args, **kwargs):
        seen_kwargs.append(kwargs)
        return responses.pop(0)

    async def fake_stream_async(*args, **kwargs):
        return fake_stream(*args, **kwargs)

    monkeypatch.setattr(c, "process_stream_response", fake_stream)
    monkeypatch.setattr(c, "process_stream_response_async", fake_stream_async)
    return c


def _tool_messages(kwargs):
    return [m for m in kwargs["messages"] if m.get("role") == "tool"]


def _barrier_tool(n):
    barrier = threading.Barrier(n, timeout=5)

    def execute_tool_fn(name, args, **kw):
        barrier.wait()  # only passes if all n calls run at once
        return f"r{args['i']}"

    return execute_tool_fn


def _run(c, fn, parallel=None):
    kwargs = dict(
        messages=[{"role": "user", "content": "go"}], tools=[], execute_tool_fn=fn,
        stream=True, verbose=False, max_iterations=3,
    )
    if parallel is not None:
        kwargs["parallel_tool_calls"] = parallel
    return asyncio.run(c.achat_completion_with_tools(**kwargs))


def test_async_parallel_runs_concurrently_and_keeps_order(monkeypatch):
    seen = []
    c = _client(monkeypatch, [_call(0), _call(1), _call(2)], seen)
    _run(c, _barrier_tool(3), parallel=True)

    tool_msgs = _tool_messages(seen[1])
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_0", "call_1", "call_2"]
    assert [json.loads(m["content"]) for m in tool_msgs] == ["r0", "r1", "r2"]
    # Loop setting only: never forwarded to the API request.
    assert all("parallel_tool_calls" not in k for k in seen)


def _concurrency_probe():
    lock = threading.Lock()
    state = {"active": 0, "max": 0}

    def execute_tool_fn(name, args, **kw):
        with lock:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
        threading.Event().wait(0.05)
        with lock:
            state["active"] -= 1
        return "ok"

    return execute_tool_fn, state


@pytest.mark.parametrize("parallel", [None, False])
def test_default_stays_sequential(monkeypatch, parallel):
    seen = []
    c = _client(monkeypatch, [_call(0), _call(1), _call(2)], seen)
    fn, state = _concurrency_probe()
    _run(c, fn, parallel=parallel)
    assert state["max"] == 1
    assert len(_tool_messages(seen[1])) == 3


def test_write_conflict_forces_sequential(monkeypatch):
    seen = []
    batch = [
        _call(0, "write_file", {"path": "/tmp/same.txt", "content": "a"}),
        _call(1, "write_file", {"path": "/tmp/same.txt", "content": "b"}),
    ]
    c = _client(monkeypatch, batch, seen)
    fn, state = _concurrency_probe()
    _run(c, fn, parallel=True)
    assert state["max"] == 1
    assert [m["tool_call_id"] for m in _tool_messages(seen[1])] == ["call_0", "call_1"]


def test_parallel_tool_error_and_bad_json_reported_in_order(monkeypatch):
    seen = []
    bad = SimpleNamespace(id="call_bad", type="function",
                          function=SimpleNamespace(name="slow", arguments="{not json"))
    c = _client(monkeypatch, [_call(0), bad, _call(2)], seen)

    def execute_tool_fn(name, args, **kw):
        if args["i"] == 0:
            raise RuntimeError("boom")
        return "ok"

    _run(c, execute_tool_fn, parallel=True)
    tool_msgs = _tool_messages(seen[1])
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_0", "call_bad", "call_2"]
    assert json.loads(tool_msgs[0]["content"]) == {"error": "boom"}
    assert "Invalid arguments JSON" in tool_msgs[1]["content"]
    assert json.loads(tool_msgs[2]["content"]) == "ok"


def _record_registered(monkeypatch):
    import praisonaiagents.llm.openai_client as oc
    registered = []
    real = oc._handle_native_deferred_result

    def spy(tool_result, messages, tool_call_id, *a, **kw):
        registered.append(tool_call_id)
        return real(tool_result, messages, tool_call_id, *a, **kw)

    monkeypatch.setattr(oc, "_handle_native_deferred_result", spy)
    return registered


def test_sequential_registers_each_result_before_next_call(monkeypatch):
    from praisonaiagents.errors import ToolExecutionError
    seen, ran = [], []
    c = _client(monkeypatch, [_call(0), _call(1), _call(2)], seen)
    registered = _record_registered(monkeypatch)

    def execute_tool_fn(name, args, **kw):
        ran.append(args["i"])
        if args["i"] == 1:
            raise ToolExecutionError("fatal", tool_name=name)
        return "ok"

    with pytest.raises(ToolExecutionError):
        _run(c, execute_tool_fn)
    assert ran == [0, 1]  # call_2 never started
    assert registered == ["call_0"]  # call_0 registered before call_1 failed


def test_parallel_fatal_error_waits_for_and_registers_siblings(monkeypatch):
    from praisonaiagents.errors import ToolExecutionError
    seen, finished = [], []
    c = _client(monkeypatch, [_call(0), _call(1)], seen)
    registered = _record_registered(monkeypatch)

    def execute_tool_fn(name, args, **kw):
        if args["i"] == 0:
            raise ToolExecutionError("fatal", tool_name=name)
        threading.Event().wait(0.1)
        finished.append(args["i"])
        return "ok"

    with pytest.raises(ToolExecutionError):
        _run(c, execute_tool_fn, parallel=True)
    assert finished == [1]  # sibling completed before the error propagated
    assert registered == ["call_1"]
