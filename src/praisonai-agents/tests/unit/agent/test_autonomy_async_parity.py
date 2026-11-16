"""G-14: run_autonomous_async must take the file snapshot and emit the
autonomy callbacks that run_autonomous does.

The async twin skipped the pre-run ``FileSnapshot.track()`` (so
``autonomy={"snapshot": True}`` gave no undo point) and emitted none of the
``autonomy_iteration`` / ``autonomy_stage_change`` / ``autonomy_doom_loop`` /
``autonomy_complete`` callbacks the CLI and UIs listen to.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent
from praisonaiagents.main import register_display_callback, sync_display_callbacks

EVENTS = ("autonomy_iteration", "autonomy_complete", "autonomy_stage_change", "autonomy_doom_loop")
_BODY = json.dumps({
    "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "still working"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}).encode()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(_BODY)))
        self.end_headers()
        self.wfile.write(_BODY)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub(monkeypatch, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    saved = {k: sync_display_callbacks.get(k) for k in EVENTS}
    yield
    for k, v in saved.items():
        if v is None:
            sync_display_callbacks.pop(k, None)
        else:
            sync_display_callbacks[k] = v
    server.shutdown()


class _FakeSnapshot:
    def __init__(self):
        self.calls = 0

    def track(self, message=None):
        self.calls += 1
        return type("Info", (), {"commit_hash": f"c{self.calls}"})()


def _run(mode):
    events = []
    for name in EVENTS:
        register_display_callback(name, (lambda n: lambda **kw: events.append((n, {k: v for k, v in kw.items() if k != "duration_seconds"})))(name))
    agent = Agent(name="g", instructions="hi", llm="gpt-4o-mini", output="silent",
                  autonomy={"snapshot": True, "max_iterations": 3})
    snapshot = _FakeSnapshot()
    agent._file_snapshot = snapshot
    if mode == "sync":
        result = agent.run_autonomous("keep going", completion_promise="DONE")
    else:
        result = asyncio.run(agent.run_autonomous_async("keep going", completion_promise="DONE"))
    return result, snapshot.calls, agent._snapshot_stack, events


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_snapshot_and_callbacks(stub, mode):
    result, snapshots, stack, events = _run(mode)
    assert result.completion_reason == "max_iterations"
    assert snapshots == 1 and stack == ["c1"]
    assert [e for e, _ in events].count("autonomy_iteration") == 3
    assert events[-1] == ("autonomy_complete", {"completion_reason": "max_iterations", "iterations": 3})


def test_sync_and_async_emit_the_same_events(stub):
    assert _run("sync")[3] == _run("async")[3]


def test_async_cancel_during_snapshot_propagates_and_keeps_partial_result(stub):
    """Cancelling while track() blocks raises CancelledError (G-07) and the
    cancelled partial result stays reachable on the agent."""
    gate = threading.Event()
    holder = {}

    class _Blocking(_FakeSnapshot):
        def track(self, message=None):
            gate.wait(5)
            return super().track(message)

    async def main():
        agent = holder["agent"] = Agent(name="g", instructions="hi", llm="gpt-4o-mini", output="silent",
                                        autonomy={"snapshot": True, "max_iterations": 3})
        agent._file_snapshot = _Blocking()
        task = asyncio.create_task(agent.run_autonomous_async("keep going", completion_promise="DONE"))
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            return await task
        finally:
            gate.set()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main())
    result = holder["agent"]._last_autonomy_result
    assert result.completion_reason == "cancelled"
    assert result.iterations == 0
