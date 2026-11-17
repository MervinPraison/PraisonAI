"""P-2 / G-12 part 1: a refused connection fails fast on ``chat()`` and ``achat()``.

Nothing listening on the port means retrying the same endpoint can only
delay the error. The classifier called it ``overloaded`` and retryable, so
``achat()`` retried it for 48.7 s; ``chat()`` failed in 3.5 s only because its
retry loop never saw the error. A refused connection is now not retryable
on either path (a fallback to another model is still allowed).
"""

import asyncio
import json
import socket
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
        code = 429 if STATE["kind"] == "429" else 500
        body = json.dumps({"error": {"message": f"stub {code}", "type": "server_error", "code": str(code)}}).encode()
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


def _closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here now: connections are refused
    return port


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


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])  # localhost: IPv6 + IPv4 attempts
@pytest.mark.parametrize("retry", [None, FAST_RETRY], ids=["default_retry", "custom_retry"])
@pytest.mark.parametrize("mode", ["chat", "achat"])
def test_refused_connection_fails_fast(stub, mode, retry, host):
    url = f"http://{host}:{_closed_port()}/v1"
    stub.setenv("OPENAI_BASE_URL", url)
    stub.setenv("OPENAI_API_BASE", url)
    stub.delenv("OPENAI_MAX_RETRIES")  # even with the SDK's own retries on
    kwargs = {} if retry is None else {"retry": retry}
    result, seconds, agent = _turn(mode, **kwargs)
    assert result is None and agent._last_error is not None
    assert seconds < 5, f"{mode}: a refused connection took {seconds:.1f}s to fail"


def _provider_error(cls, cause):
    import httpx
    import openai
    request = httpx.Request("POST", "http://127.0.0.1:1/v1/chat/completions")
    try:
        try:
            raise cause
        except Exception as inner:
            raise cls(request=request) from inner
    except openai.APIConnectionError as e:
        return e


def test_classifier_refused_is_not_retryable_but_timeouts_still_are():
    import httpx
    import openai
    from praisonaiagents.llm.error_classifier import classify_llm_error
    refused = _provider_error(openai.APIConnectionError, httpx.ConnectError("[Errno 61] Connection refused"))
    refused.__cause__.__cause__ = ConnectionRefusedError(61, "Connection refused")
    timeout = _provider_error(openai.APITimeoutError, httpx.ReadTimeout("timed out"))
    c_refused = classify_llm_error(refused, provider="openai", model="gpt-4o-mini")
    c_timeout = classify_llm_error(timeout, provider="openai", model="gpt-4o-mini")
    assert not c_refused.is_retryable and c_refused.should_fallback_model  # a fallback model may still help
    assert c_timeout.is_retryable
    c_503 = classify_llm_error(RuntimeError("503 Service Unavailable"), provider="openai", model="m")
    assert c_503.is_retryable
