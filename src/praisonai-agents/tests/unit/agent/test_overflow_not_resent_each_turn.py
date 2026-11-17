"""After one context overflow, later turns must not re-send the rejected size (R-05)."""

import http.server
import json
import threading

import pytest

LIMIT = 20_000


class _Stub(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length", 0)))
        rejected = len(raw) > LIMIT
        _Stub.hits.append(rejected)
        if rejected:
            body = json.dumps({"error": {
                "message": "This model's maximum context length is 128000 tokens. However, your "
                           "messages resulted in 130000 tokens. Please reduce the length of the messages.",
                "type": "invalid_request_error", "param": "messages", "code": "context_length_exceeded"}}).encode()
            self.send_response(400)
        else:
            body = json.dumps({
                "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "word " * 80}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
            self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def base_url(monkeypatch):
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("OPENAI_BASE_URL", url)
    monkeypatch.setenv("OPENAI_API_BASE", url)
    _Stub.hits = []
    yield url
    srv.shutdown()


def _run_turns(send):
    rejected_turns, turn = [], 0
    for turn in range(1, 50):
        start = len(_Stub.hits)
        assert send("question " * 20)
        if any(_Stub.hits[start:]):
            rejected_turns.append(turn)
        if len(rejected_turns) > 1 or (rejected_turns and turn - rejected_turns[0] >= 8):
            break
    assert rejected_turns, "stub never overflowed; raise the turn count"
    return rejected_turns, turn


def test_turns_after_an_overflow_do_not_resend_the_rejected_size(base_url):
    from praisonaiagents import Agent

    agent = Agent(name="s", instructions="hi", model="gpt-4o-mini", output="silent")
    rejected_turns, turns = _run_turns(agent.chat)
    assert len(rejected_turns) == 1, f"overflow re-sent on turns {rejected_turns}"
    # The agent's own history is not trimmed; only the request is.
    assert len([m for m in agent.chat_history if m["role"] == "user"]) == turns


def test_async_turns_after_an_overflow_do_not_resend(base_url):
    import asyncio
    from praisonaiagents import Agent

    agent = Agent(name="s", instructions="hi", model="gpt-4o-mini", output="silent")
    rejected_turns, _ = _run_turns(lambda p: asyncio.run(agent.achat(p)))
    assert len(rejected_turns) == 1, f"overflow re-sent on turns {rejected_turns}"
