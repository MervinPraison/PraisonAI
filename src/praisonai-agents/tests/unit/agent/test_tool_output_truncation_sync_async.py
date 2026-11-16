"""G-04 (truncation half): async tool output must be capped like sync.

A tool returning 400,000 characters reached the model as a 17.6 KB follow-up
request on ``chat()`` and a 401.5 KB one on ``achat()``: the async tool path
never applied the tool-output limit.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent

_TOOL_MESSAGES = []


def _reply(messages, tools):
    if tools and not any(m.get("role") == "tool" for m in messages):
        msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": tools[0]["function"]["name"], "arguments": "{}"}}]}
        return msg, "tool_calls"
    _TOOL_MESSAGES.extend(m["content"] for m in messages if m.get("role") == "tool")
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
    _TOOL_MESSAGES.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    # OPENAI_API_BASE takes precedence over OPENAI_BASE_URL; CI sets it.
    monkeypatch.setenv("OPENAI_BASE_URL", base_url)
    monkeypatch.setenv("OPENAI_API_BASE", base_url)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield
    server.shutdown()


def big_tool() -> str:
    """Return a large payload."""
    return "x" * 400_000


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_large_tool_output_is_capped(stub, mode):
    agent = Agent(name="t", instructions="hi", llm="gpt-4o-mini", tools=[big_tool], output="silent")
    result = agent.chat("go") if mode == "sync" else asyncio.run(agent.achat("go"))
    assert result == "done"
    assert len(_TOOL_MESSAGES) == 1
    sent = _TOOL_MESSAGES[0]
    assert len(sent) < 50_000, f"{mode}: {len(sent):,} chars of tool output sent to the model"
    assert "400,000" in sent  # the truncation marker names the original size


def test_sync_and_async_send_the_same_capped_output(stub):
    sizes = []
    for run in (lambda a: a.chat("go"), lambda a: asyncio.run(a.achat("go"))):
        _TOOL_MESSAGES.clear()
        run(Agent(name="t", instructions="hi", llm="gpt-4o-mini", tools=[big_tool], output="silent"))
        sizes.append(len(_TOOL_MESSAGES[0]))
    assert sizes[0] == sizes[1]


def echo(x: int) -> int:
    """echo"""
    return x


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_agent_deepcopies_after_tool_use(monkeypatch, mode):
    # Capping a tool result builds the lazy ContextManager (it holds locks).
    # A clone must rebuild its own rather than fail to deep-copy it; on main
    # this already failed after a sync tool call.
    import copy
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    agent = Agent(name="d", instructions="x", tools=[echo], llm="gpt-4o-mini")
    run = (lambda a, x: a.execute_tool("echo", {"x": x})) if mode == "sync" else \
          (lambda a, x: asyncio.run(a.execute_tool_async("echo", {"x": x})))
    assert run(agent, 1) == 1
    clone = copy.deepcopy(agent)
    assert clone.context_manager is not None
    assert clone.context_manager is not agent.context_manager
    assert run(clone, 2) == 2


def test_oversized_error_dict_stays_an_error_dict(monkeypatch):
    # Many medium fields push the dict over the total budget; the capped
    # result must still carry ``error`` (and its flags) so retry, loop-guard
    # and circuit-breaker checks still see a failure.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    agent = Agent(name="e", instructions="x", llm="gpt-4o-mini", context=False)
    big = {"error": "rate limit", "approval_denied": False,
           **{f"f{i}": "y" * 4_000 for i in range(50)}}
    capped = agent._truncate_tool_result("t", big, "call_1")
    assert isinstance(capped, dict)
    assert capped["error"] and capped["approval_denied"] is False
    assert len(str(capped)) < 50_000


def test_deepcopy_keeps_assigned_context_manager(monkeypatch):
    # A manager assigned via the public setter is the user's, not lazily
    # built: the clone gets a copy of it, not a fresh default or None.
    import copy

    class _Mgr:
        marker = "custom"

    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    agent = Agent(name="m", instructions="x", llm="gpt-4o-mini", context=False)
    agent.context_manager = _Mgr()
    clone = copy.deepcopy(agent)
    assert isinstance(clone.context_manager, _Mgr)
