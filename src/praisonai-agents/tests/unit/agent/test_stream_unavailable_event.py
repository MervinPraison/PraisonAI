"""X-04: falling back from streaming tells stream consumers.

``StreamEventType.STREAM_UNAVAILABLE`` was defined (and mapped for AG-UI) but
emitted nowhere: when the sync adapter cannot stream, the turn quietly ran
unstreamed. It is now emitted once at each fallback, only when someone is
listening.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent
from praisonaiagents.streaming.events import StreamEventType

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


def _kinds(stream):
    agent = Agent(name="s", instructions="hi", model="gpt-4o-mini", output="silent")
    events = []
    agent.stream_emitter.add_callback(events.append)
    assert agent.chat("hi", stream=stream) == "hello"
    return [e.type for e in events]


def test_sync_fallback_emits_stream_unavailable_once(stub):
    kinds = _kinds(True)
    assert kinds.count(StreamEventType.STREAM_UNAVAILABLE) == 1, kinds


def test_no_event_when_streaming_was_not_requested(stub):
    assert StreamEventType.STREAM_UNAVAILABLE not in _kinds(False)
