"""G-02 (warning only): a failed LLM call still returns None, but says so.

``start()``/``chat()``/``achat()`` printed an error panel and returned None
when the LLM call failed, so ``agent.start(...).upper()`` broke later with an
unrelated AttributeError and the cause was gone. In 1.x the return value stays
None (backward compatible); the turn now emits a FutureWarning and keeps the
exception on ``agent._last_error``.
"""

import asyncio
import json
import threading
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent

_ERR = json.dumps({"error": {"message": "Incorrect API key provided", "type": "invalid_request_error",
                             "code": "invalid_api_key"}}).encode()
_OK = json.dumps({
    "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
}).encode()
STATE = {"fail": True}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        status, body = (401, _ERR) if STATE["fail"] else (200, _OK)
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub(monkeypatch, tmp_path):
    STATE["fail"] = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-bad")
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    # Pin the legacy name too: a value leaked by another test would win
    # and send the "next turn succeeds" call to the wrong endpoint.
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield base
    server.shutdown()


def _agent(base, route):
    if route == "openai_client":
        return Agent(name="w", instructions="hi", llm="gpt-4o-mini", output="silent", retry=False)
    return Agent(name="w", instructions="hi", llm="openai/local-model", base_url=base, api_key="sk-bad",
                 output="silent", retry=False)


@pytest.mark.parametrize("route", ["openai_client", "custom_llm"])
@pytest.mark.parametrize("mode", ["chat", "achat", "start"])
def test_failed_turn_returns_none_warns_and_keeps_error(stub, mode, route):
    agent = _agent(stub, route)
    assert agent._last_error is None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if mode == "chat":
            result = agent.chat("hi")
        elif mode == "achat":
            result = asyncio.run(agent.achat("hi"))
        else:
            result = agent.start("hi")
    assert result is None  # 1.x contract unchanged
    future = [w for w in caught if issubclass(w.category, FutureWarning) and "returning None" in str(w.message)]
    assert len(future) == 1, [str(w.message) for w in caught]
    assert agent._last_error is not None
    assert "_last_error" in str(future[0].message)


@pytest.mark.parametrize("route", ["openai_client", "custom_llm"])
@pytest.mark.parametrize("mode", ["chat", "achat"])
def test_warnings_as_errors_keeps_none_and_original_error(stub, mode, route):
    agent = _agent(stub, route)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        result = agent.chat("hi") if mode == "chat" else asyncio.run(agent.achat("hi"))
    assert result is None
    assert agent._last_error is not None
    assert not isinstance(agent._last_error, Warning)


def test_warning_text_is_stable_across_failures():
    from praisonaiagents.agent.chat_mixin import ChatMixin

    m = ChatMixin()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        m._none_after_failed_turn(RuntimeError("request id abc"))
        m._none_after_failed_turn(RuntimeError("request id xyz"))
    assert len({str(w.message) for w in caught}) == 1


def test_next_successful_turn_clears_the_error(stub):
    agent = _agent(stub, "openai_client")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert agent.chat("hi") is None
    assert agent._last_error is not None
    STATE["fail"] = False
    assert agent.chat("hi again") == "hello"
    assert agent._last_error is None
