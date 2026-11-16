"""G-04 (trace half): async tool calls must emit tool trace events like sync.

``chat()`` emitted ``tool_call_start`` / ``tool_call_end`` around every tool
call; ``achat()`` emitted neither, so traces and replays of async runs showed
LLM calls with no tools in between.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent
from praisonaiagents.trace.context_events import (
    ContextEventType,
    ContextListSink,
    ContextTraceEmitter,
    trace_context,
)


def _reply(messages, tools):
    if tools and not any(m.get("role") == "tool" for m in messages):
        msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": tools[0]["function"]["name"], "arguments": "{}"}}]}
        return msg, "tool_calls"
    return {"role": "assistant", "content": "done"}, "stop"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        msg, finish = _reply(req.get("messages", []), req.get("tools"))
        body = json.dumps({
            "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub(monkeypatch, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    # OPENAI_API_BASE wins over OPENAI_BASE_URL (CI sets it), so pin both to the stub.
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield
    server.shutdown()


def lookup() -> str:
    """Look something up."""
    return "found it"


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_tool_call_emits_start_and_end(stub, mode):
    sink = ContextListSink()
    agent = Agent(name="t", instructions="hi", llm="gpt-4o-mini", tools=[lookup], output="silent")
    with trace_context(ContextTraceEmitter(sink=sink, session_id="s", enabled=True)):
        result = agent.chat("go") if mode == "sync" else asyncio.run(agent.achat("go"))
    assert result == "done"
    tool_events = [e for e in sink.get_events()
                   if e.event_type in (ContextEventType.TOOL_CALL_START, ContextEventType.TOOL_CALL_END)]
    assert [e.event_type for e in tool_events] == [ContextEventType.TOOL_CALL_START, ContextEventType.TOOL_CALL_END]
    assert "found it" in str(tool_events[1].data)


def test_cancelled_async_tool_still_emits_end(monkeypatch):
    sink = ContextListSink()
    agent = Agent(name="t", instructions="hi", llm="gpt-4o-mini", output="silent")

    async def _cancelled(*args, **kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(agent, "_execute_tool_async_retry_loop", _cancelled)
    with trace_context(ContextTraceEmitter(sink=sink, session_id="s", enabled=True)):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(agent._execute_tool_async_with_retry("lookup", {}))
    tool_events = [e for e in sink.get_events()
                   if e.event_type in (ContextEventType.TOOL_CALL_START, ContextEventType.TOOL_CALL_END)]
    assert [e.event_type for e in tool_events] == [ContextEventType.TOOL_CALL_START, ContextEventType.TOOL_CALL_END]
    assert "CancelledError" in str(tool_events[1].data)
