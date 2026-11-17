"""R-04: in a terminal, ``start()`` returns as soon as the turn ends.

The animated-status loop polled the chat thread with ``time.sleep(0.15)``, so
every terminal turn paid up to 150 ms after the answer was ready (median 157 ms
against 3 ms when not a terminal). It now waits on the thread itself.
"""

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
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    # OPENAI_API_BASE wins over OPENAI_BASE_URL and CI exports it: pin both.
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield
    server.shutdown()
    server.server_close()


def test_terminal_turn_does_not_poll_with_sleep(stub, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    sleeps = []
    real_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda s: (sleeps.append(s), real_sleep(s))[1])
    agent = Agent(name="t", instructions="hi", model="gpt-4o-mini")
    assert agent.start("hi", stream=False) == "hello"
    assert 0.15 not in sleeps, "start() polled the chat thread with sleep(0.15)"
