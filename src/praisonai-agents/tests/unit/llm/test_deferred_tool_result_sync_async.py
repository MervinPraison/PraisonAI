"""G-06: a ``defer(...)`` tool result must be registered on every LLM tool loop.

Only the sync Responses-route loop (which runs tools through the call
executor) registered the deferred handle and sent the model its note. The
async loop, and the sync Chat Completions loop, called the tool directly, so
the handle was never registered (its eventual value was lost) and the model
got ``str(DeferredToolResult(...))``.
"""

import asyncio
import itertools
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents.llm.llm import LLM
from praisonaiagents.tools.call_executor import defer, get_deferred_resolver

TOOLS = [{"type": "function", "function": {
    "name": "research", "description": "long job", "parameters": {"type": "object", "properties": {}}}}]
SEEN_TOOL_OUTPUT = []
N_CALLS = [1]  # tool calls the stub returns per turn; >1 exercises the real parallel branches


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        if self.path.endswith("/responses"):
            outputs = [i for i in req.get("input", []) if isinstance(i, dict) and i.get("type") == "function_call_output"]
            SEEN_TOOL_OUTPUT.extend(str(i.get("output")) for i in outputs)
            if outputs or not req.get("tools"):
                out = [{"type": "message", "id": "m1", "status": "completed", "role": "assistant",
                        "content": [{"type": "output_text", "text": "started", "annotations": []}]}]
            else:
                out = [{"type": "function_call", "id": f"fc_{i}", "call_id": f"call_{i}", "name": "research",
                        "arguments": "{}", "status": "completed"} for i in range(N_CALLS[0])]
            return self._send({"id": "r1", "object": "response", "created_at": 0, "status": "completed",
                               "model": "gpt-4o-mini", "output": out,
                               "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                               "parallel_tool_calls": True, "tool_choice": "auto", "tools": []})
        msgs = req.get("messages", [])
        tool_msgs = [m for m in msgs if m.get("role") == "tool"]
        SEEN_TOOL_OUTPUT.extend(str(m.get("content")) for m in tool_msgs)
        if req.get("tools") and not tool_msgs:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call_{i}", "type": "function", "function": {"name": "research", "arguments": "{}"}}
                for i in range(N_CALLS[0])]}
            fin = "tool_calls"
        else:
            msg, fin = {"role": "assistant", "content": "started"}, "stop"
        self._send({"id": "c1", "object": "chat.completion", "created": 0, "model": "local-model",
                    "choices": [{"index": 0, "message": msg, "finish_reason": fin}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    def log_message(self, *args):
        pass


@pytest.fixture
def base(monkeypatch):
    SEEN_TOOL_OUTPUT.clear()
    N_CALLS[0] = 1
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_BASE_URL", url)  # Responses route without relying on G-01
    monkeypatch.setenv("OPENAI_API_BASE", url)
    yield url
    server.shutdown()


def _llm(route, base):
    if route == "chat":
        return LLM(model="openai/local-model", base_url=base, api_key="x")
    llm = LLM(model="gpt-4o-mini", api_key="x", api_base=base)
    assert llm._supports_responses_api()
    return llm


def _run(llm, mode, execute_tool, parallel):
    kwargs = dict(prompt="go", tools=TOOLS, execute_tool_fn=execute_tool, verbose=False, stream=False,
                  parallel_tool_calls=parallel)
    return llm.get_response(**kwargs) if mode == "sync" else asyncio.run(llm.get_response_async(**kwargs))


@pytest.mark.parametrize("parallel", [False, True])
@pytest.mark.parametrize("route", ["chat", "responses"])
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_deferred_tool_result_is_registered(base, route, mode, parallel):
    N_CALLS[0] = 2 if parallel else 1
    resolver = get_deferred_resolver()
    handles = [f"g06-{route}-{mode}-{parallel}-{i}" for i in range(N_CALLS[0])]
    for h in handles:
        resolver.cancel(h)
    counter = itertools.count()

    def execute_tool(name, args, *a, **k):
        return defer(note="research started", handle_id=handles[next(counter) % len(handles)])

    try:
        assert _run(_llm(route, base), mode, execute_tool, parallel) == "started"
        assert all(resolver.is_pending(h) for h in handles)
        assert len(SEEN_TOOL_OUTPUT) >= len(handles)
        assert all("research started" in s and "DeferredToolResult" not in s for s in SEEN_TOOL_OUTPUT)
    finally:
        for h in handles:
            resolver.cancel(h)


def test_async_parallel_failing_sibling_keeps_deferred_handle(base):
    """A sibling that raises must not orphan another tool's deferred job."""
    N_CALLS[0] = 2
    resolver = get_deferred_resolver()
    handle = "g06-async-failing-sibling"
    resolver.cancel(handle)
    counter = itertools.count()

    def execute_tool(name, args, *a, **k):
        if next(counter) == 0:
            return defer(note="research started", handle_id=handle)
        raise RuntimeError("sibling failed")

    try:
        try:
            _run(_llm("chat", base), "async", execute_tool, True)
        except Exception:  # noqa: BLE001 — propagation is not what this test checks
            pass
        assert resolver.is_pending(handle)
    finally:
        resolver.cancel(handle)
