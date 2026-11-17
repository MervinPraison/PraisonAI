"""P-2 / G-12: ``chat()`` and ``achat()`` retry a failing model call the same way.

Sync nested the ``RetryBackoffConfig`` loop inside the error classifier, so the
loop saw raw provider errors and never retried; async nested them the other way
round, so retryable errors were retried by both layers. And the classifier
sent every transient error (5xx, timeout, overloaded) to its model-fallback
branch, which without fallback models gave up. On a refused port that was
3.5 s on ``chat()`` and 48.7 s on ``achat()``.

Contract: one retry layer on both paths; retryable errors (timeout, 5xx, 429)
are retried ``retry.max_retries`` times; ``retry=False`` means one attempt.
(A refused connection is not retried: ``test_refused_connection_fails_fast.py``.)
The SDK's own retries are turned off (``OPENAI_MAX_RETRIES=0``) so the stub
counts our attempts only.
"""

import asyncio
import json
import threading
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent

HITS = []
STATE = {"kind": "500"}
FAST_RETRY = {"max_retries": 2, "base_delay": 0.01, "max_delay": 0.02, "jitter_ratio": 0.0}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        HITS.append(time.monotonic())
        if STATE["kind"] == "timeout":
            time.sleep(1.5)  # past OPENAI_TIMEOUT
        if STATE["kind"] == "overflow":
            code, err = 400, {"message": "This model's maximum context length is 8192 tokens.",
                              "type": "invalid_request_error", "code": "context_length_exceeded"}
        else:
            code = 429 if STATE["kind"] == "429" else 500
            err = {"message": f"stub {code}", "type": "server_error", "code": str(code)}
        body = json.dumps({"error": err}).encode()
        try:
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass  # the client already timed out

    def log_message(self, *args):
        pass


@pytest.fixture
def stub(monkeypatch, tmp_path):
    HITS.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    # OPENAI_API_BASE wins over OPENAI_BASE_URL and CI exports it: pin both.
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "0")
    monkeypatch.setenv("OPENAI_TIMEOUT", "0.5")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield monkeypatch
    server.shutdown()


def _turn(mode, **kwargs):
    agent = Agent(name="r", instructions="hi", llm="gpt-4o-mini", output="silent", **kwargs)
    start = time.monotonic()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = agent.chat("hi") if mode == "chat" else asyncio.run(agent.achat("hi"))
    return result, time.monotonic() - start, agent


@pytest.mark.parametrize("kind", ["500", "429", "timeout"])
@pytest.mark.parametrize("mode", ["chat", "achat"])
def test_retryable_errors_are_retried_max_retries_times(stub, mode, kind):
    STATE["kind"] = kind
    result, _, agent = _turn(mode, retry=FAST_RETRY)
    assert result is None and agent._last_error is not None
    assert len(HITS) == 1 + FAST_RETRY["max_retries"]


@pytest.mark.parametrize("kind", ["500", "429", "timeout"])
@pytest.mark.parametrize("mode", ["chat", "achat"])
def test_retry_false_makes_one_attempt(stub, mode, kind):
    STATE["kind"] = kind
    result, _, _ = _turn(mode, retry=False)
    assert result is None
    assert len(HITS) == 1



def test_context_overflow_is_not_resent_unchanged(stub):
    # Only compression fixes an overflow: its own restarts (bounded by
    # max_retries) still run, but the backoff layer must not also resend the
    # same messages (7 requests instead of 3 before the fix).
    STATE["kind"] = "overflow"
    result, _, agent = _turn("chat", retry=FAST_RETRY)
    assert result is None and agent._last_error is not None
    assert len(HITS) <= 1 + FAST_RETRY["max_retries"]
