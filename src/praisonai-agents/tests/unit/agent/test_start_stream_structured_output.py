"""start(output_pydantic=...) must not silently turn into a raw-text stream (D-08)."""

import http.server
import json
import sys
import threading
import warnings

import pytest
from pydantic import BaseModel


class Out(BaseModel):
    city: str


class _Stub(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        content = json.dumps({"city": "Paris"})
        if req.get("stream"):
            chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m",
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]}
            end = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            body = f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(end)}\n\ndata: [DONE]\n\n".encode()
            ctype = "text/event-stream"
        else:
            body = json.dumps({"id": "c", "object": "chat.completion", "created": 0, "model": "m",
                               "choices": [{"index": 0, "finish_reason": "stop",
                                            "message": {"role": "assistant", "content": content}}],
                               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            ctype = "application/json"
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def agent(monkeypatch):
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_BASE_URL", url)
    monkeypatch.setenv("OPENAI_API_BASE", url)
    from praisonaiagents import Agent
    yield Agent(name="s", instructions="hi", model="gpt-4o-mini")
    srv.shutdown()


def test_terminal_auto_stream_still_returns_the_model(agent, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    result = agent.start("Where?", output_pydantic=Out)
    assert isinstance(result, Out), type(result)


def test_explicit_stream_with_output_pydantic_warns(agent):
    with pytest.warns(UserWarning, match="output_pydantic"):
        result = agent.start("Where?", output_pydantic=Out, stream=True)
    assert "".join(result)  # still the stream the caller asked for


def test_plain_stream_does_not_warn(agent):
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        assert "".join(agent.start("Where?", stream=True))
