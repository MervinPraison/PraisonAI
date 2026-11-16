"""G-09: sync ``chat()`` turns must reuse one ``AsyncOpenAI`` client.

The default sync path runs the async OpenAI loop through the async bridge,
which used ``asyncio.run`` per turn: a fresh event loop every time, so the
loop-bound ``AsyncOpenAI`` client (and its HTTP keep-alive pool) was dropped
and rebuilt on every turn (10 chats built it 10 times).
"""

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent
from praisonaiagents.utils import async_bridge

needs_runner = pytest.mark.skipif(sys.version_info < (3, 11), reason="asyncio.Runner is 3.11+; 3.10 keeps asyncio.run")
PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_BODY = json.dumps({
    "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
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
    monkeypatch.setenv("OPENAI_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}/v1")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield
    server.shutdown()


@needs_runner
def test_ten_sync_chats_build_one_async_client(stub, monkeypatch):
    import openai
    built = []
    real_init = openai.AsyncOpenAI.__init__

    def counting_init(self, *args, **kwargs):
        built.append(1)
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(openai.AsyncOpenAI, "__init__", counting_init)
    agent = Agent(name="c", instructions="hi", llm="gpt-4o-mini", output="silent")
    for i in range(10):
        assert agent.chat(f"hi {i}") == "hello"
    assert len(built) == 1


@needs_runner
def test_each_sync_turn_sees_the_callers_current_context(stub):
    # A long-lived loop must not freeze the context of the first call: each
    # turn's trace events go to the emitter active for *that* call.
    from praisonaiagents.trace.context_events import ContextListSink, ContextTraceEmitter, trace_context
    agent = Agent(name="c", instructions="hi", llm="gpt-4o-mini", output="silent")
    sinks = [ContextListSink(), ContextListSink()]
    for sink in sinks:
        with trace_context(ContextTraceEmitter(sink=sink, session_id="s", enabled=True)):
            agent.chat("hi")
    assert all(len(s) > 0 for s in sinks)
    assert len(sinks[0]) == len(sinks[1])


@needs_runner
def test_thread_loop_is_reused_per_thread_and_replaced_after_fork(monkeypatch):
    async def current_loop():
        return asyncio.get_running_loop()

    first = async_bridge.run_coroutine_on_thread_loop(current_loop(), timeout=None)
    assert async_bridge.run_coroutine_on_thread_loop(current_loop(), timeout=None) is first

    other = []
    t = threading.Thread(target=lambda: other.append(
        async_bridge.run_coroutine_on_thread_loop(current_loop(), timeout=None)))
    t.start(); t.join()
    assert other[0] is not first  # threads never share a loop

    real_pid = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: real_pid + 1)  # as after os.fork()
    assert async_bridge.run_coroutine_on_thread_loop(current_loop(), timeout=None) is not first


def test_inside_a_running_loop_still_offloads(monkeypatch):
    async def outer():
        async def inner():
            return threading.current_thread().name
        return async_bridge.run_coroutine_on_thread_loop(inner(), timeout=5)

    assert asyncio.run(outer()) == "praisonai-async-bridge"


def test_interpreter_exits_cleanly_after_sync_turns(tmp_path):
    script = textwrap.dedent('''
        import json, os, threading, http.server, io, contextlib
        os.environ["OPENAI_API_KEY"] = "sk-local-fake"
        B = %r
        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def do_POST(self):
                self.rfile.read(int(self.headers.get("content-length", 0)))
                self.send_response(200); self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(B))); self.end_headers(); self.wfile.write(B)
            def log_message(self, *a): pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        os.environ["OPENAI_BASE_URL"] = "http://127.0.0.1:%%d/v1" %% srv.server_address[1]
        from praisonaiagents import Agent
        a = Agent(name="x", instructions="hi", llm="gpt-4o-mini", output="silent")
        print(a.chat("one"), a.chat("two"))
    ''') % (_BODY,)
    env = dict(os.environ, PYTHONPATH=PKG_ROOT, PRAISONAI_HOME=str(tmp_path), PYTHONWARNINGS="default")
    env.pop("OPENAI_BASE_URL", None)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                          cwd=str(tmp_path), env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == "hello hello"
    for noise in ("Event loop is closed", "Task was destroyed", "Task exception was never retrieved", "Traceback"):
        assert noise not in proc.stderr, proc.stderr[-2000:]
