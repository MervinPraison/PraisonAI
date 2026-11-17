"""G-07: cancelling an async autonomous run must propagate.

``run_autonomous_async`` turned ``asyncio.CancelledError`` into a returned
``AutonomyResult(completion_reason="cancelled")``, so ``asyncio.wait_for``,
``TaskGroup`` and ``task.cancel()`` could not tell the run was cancelled.
The sync Ctrl-C result is a feature and is unchanged.
"""

import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent

_BODY = json.dumps({
    "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
}).encode()


class _SlowHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        time.sleep(2.0)
        try:
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(_BODY)))
            self.end_headers()
            self.wfile.write(_BODY)
        except OSError:
            pass  # client went away after cancellation

    def log_message(self, *args):
        pass


@pytest.fixture
def slow_stub(monkeypatch, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}/v1")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield
    server.shutdown()


def _agent():
    return Agent(name="c", instructions="hi", llm="gpt-4o-mini", autonomy=True, output="silent")


def test_wait_for_timeout_raises_and_keeps_partial_result(slow_stub):
    agent = _agent()

    async def go():
        await asyncio.wait_for(agent.run_autonomous_async("say hi"), 0.3)

    started = time.perf_counter()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(go())
    assert time.perf_counter() - started < 1.9  # did not wait for the stub
    partial = agent._last_autonomy_result
    assert partial.completion_reason == "cancelled"
    assert partial.success is False


def test_task_cancel_raises_cancelled_error(slow_stub):
    agent = _agent()

    async def go():
        task = asyncio.create_task(agent.run_autonomous_async("say hi"))
        await asyncio.sleep(0.2)
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())


def test_sync_keyboard_interrupt_still_returns_result(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    agent = _agent()

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(agent, "achat", interrupted)
    result = agent.run_autonomous("say hi")
    assert result.completion_reason == "cancelled"
    assert result.success is False


def test_start_status_thread_is_daemon(monkeypatch):
    # The verbose-TTY start() path runs chat() in a helper thread; it must be a
    # daemon so Ctrl-C in the display loop cannot leave the process hanging.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    created = []
    real_thread = threading.Thread

    class _Recording(real_thread):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Thread drops _target after run(); record it now.
            created.append((getattr(kwargs.get("target"), "__name__", None), self))

    monkeypatch.setattr(threading, "Thread", _Recording)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    agent = Agent(name="d", instructions="hi", llm="gpt-4o-mini")
    monkeypatch.setattr(agent, "chat", lambda prompt, **kwargs: "ok")
    assert agent.start("hi", stream=False) == "ok"
    chat_threads = [t for name, t in created if name == "run_chat"]
    assert chat_threads, "verbose TTY path did not start the chat thread"
    assert all(t.daemon for t in chat_threads)


def test_last_autonomy_result_defaults_to_none_before_any_run():
    """Reading the attribute on an agent that never ran must not raise."""
    from praisonaiagents import Agent

    assert Agent(name="fresh", instructions="hi")._last_autonomy_result is None
