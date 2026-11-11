"""The synchronous chat-completions path honors parallel tool execution."""
import json
import threading

import pytest

litellm = pytest.importorskip("litellm")


def test_sync_parallel_dispatch_keeps_order_and_budget(monkeypatch):
    from praisonaiagents.llm.llm import LLM

    requests = []
    barrier = threading.Barrier(2)
    concurrent = []

    def completion(*args, **kwargs):
        requests.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        calls = [
            {"id": f"c{i}", "type": "function",
             "function": {"name": "ping", "arguments": json.dumps({"n": i})}}
            for i in range(3)
        ]
        message = {"role": "assistant", "content": "", "tool_calls": calls} if len(requests) == 1 else {"role": "assistant", "content": "done"}
        return litellm.ModelResponse(choices=[{"message": message, "index": 0,
                                               "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}])

    def execute(name, arguments, *, tool_call_id):
        try:
            barrier.wait(timeout=3)
            concurrent.append(tool_call_id)
        except threading.BrokenBarrierError:
            pass
        return {"value": arguments["n"]}

    monkeypatch.setattr(litellm, "completion", completion)
    llm = LLM(model="anthropic/claude-3-haiku-20240307")
    result = llm.get_response("go", tools=[{"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}}}}], execute_tool_fn=execute, parallel_tool_calls=True, max_tool_calls_per_turn=2, stream=False, verbose=False)

    assert result == "done"
    assert sorted(concurrent) == ["c0", "c1"]
    followup = requests[1]
    declared = [c["id"] for m in followup for c in m.get("tool_calls", [])]
    replies = [m["tool_call_id"] for m in followup if m.get("role") == "tool"]
    assert declared == replies == ["c0", "c1"]


def test_sync_parallel_preserves_errors_and_durable_iteration(monkeypatch):
    from praisonaiagents.llm.llm import LLM

    requests = []
    seen = []

    def completion(*args, **kwargs):
        requests.append(json.loads(json.dumps(kwargs["messages"], default=str)))
        calls = [
            {"id": "ok", "type": "function", "function": {"name": "ping", "arguments": "{}"}},
            {"id": "bad", "type": "function", "function": {"name": "ping", "arguments": "{}"}},
        ]
        message = {"role": "assistant", "content": "", "tool_calls": calls} if len(requests) == 1 else {"role": "assistant", "content": "done"}
        return litellm.ModelResponse(choices=[{"message": message, "index": 0,
                                               "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}])

    def execute(name, arguments, *, tool_call_id, _durable_iteration_index):
        seen.append((tool_call_id, _durable_iteration_index))
        if tool_call_id == "bad":
            raise ValueError("expected error")
        return "ok"

    execute._accepts_durable_iteration = True
    monkeypatch.setattr(litellm, "completion", completion)
    llm = LLM(model="anthropic/claude-3-haiku-20240307")
    tools = [{"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}}}]
    assert llm.get_response("go", tools=tools, execute_tool_fn=execute,
                            parallel_tool_calls=True, stream=False, verbose=False) == "done"
    assert sorted(seen) == [("bad", 0), ("ok", 0)]
    replies = [m for m in requests[1] if m.get("role") == "tool"]
    assert [m["tool_call_id"] for m in replies] == ["ok", "bad"]
    assert "expected error" in replies[1]["content"]


def test_sync_parallel_propagates_tool_execution_error(monkeypatch):
    from praisonaiagents.errors import ToolExecutionError
    from praisonaiagents.llm.llm import LLM

    calls = [
        {"id": str(i), "type": "function", "function": {"name": "ping", "arguments": "{}"}}
        for i in range(2)
    ]
    def completion(*args, **kwargs):
        return litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "", "tool_calls": calls}, "index": 0, "finish_reason": "tool_calls"}])

    def execute(name, arguments, *, tool_call_id):
        if tool_call_id == "0":
            raise ToolExecutionError("terminal tool failure")
        return "ok"

    monkeypatch.setattr(litellm, "completion", completion)
    llm = LLM(model="anthropic/claude-3-haiku-20240307")
    tools = [{"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}}}]
    with pytest.raises(ToolExecutionError, match="terminal tool failure"):
        llm.get_response("go", tools=tools, execute_tool_fn=execute,
                         parallel_tool_calls=True, stream=False, verbose=False)


def test_sync_parallel_error_content_matches_sequential(monkeypatch):
    from praisonaiagents.llm.llm import LLM

    messages_by_mode = []
    for parallel in (False, True):
        requests = []
        def completion(*args, **kwargs):
            requests.append(json.loads(json.dumps(kwargs["messages"], default=str)))
            calls = [
                {"id": str(i), "type": "function", "function": {"name": "ping", "arguments": "{}"}}
                for i in range(2)
            ]
            message = {"role": "assistant", "content": "", "tool_calls": calls} if len(requests) == 1 else {"role": "assistant", "content": "done"}
            return litellm.ModelResponse(choices=[{"message": message, "index": 0, "finish_reason": "tool_calls" if len(requests) == 1 else "stop"}])

        def execute(name, arguments, *, tool_call_id):
            raise ValueError("expected failure")

        monkeypatch.setattr(litellm, "completion", completion)
        llm = LLM(model="anthropic/claude-3-haiku-20240307")
        tools = [{"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}}}]
        assert llm.get_response("go", tools=tools, execute_tool_fn=execute,
                                parallel_tool_calls=parallel, stream=False, verbose=False) == "done"
        messages_by_mode.append([m["content"] for m in requests[1] if m.get("role") == "tool"])
    assert messages_by_mode[0] == messages_by_mode[1]
