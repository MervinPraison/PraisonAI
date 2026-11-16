"""G-03: ``achat()`` must persist the user message, exactly as ``chat()`` does.

The async default (OpenAI client) path appended the user turn to
``chat_history`` but never wrote it to the DB / session store, so a resumed
async session had assistant replies with no questions.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent, MemoryConfig

_CHAT = json.dumps({
    "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
}).encode()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("content-length", 0)))
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(_CHAT)))
        self.end_headers()
        self.wfile.write(_CHAT)

    def log_message(self, *args):
        pass


class _Recorder:
    def __init__(self):
        self.rows = []

    def on_agent_start(self, **kwargs):
        return []

    def on_user_message(self, session_id, content, *args, **kwargs):
        self.rows.append(("user", content))

    def on_agent_message(self, session_id, content, *args, **kwargs):
        self.rows.append(("assistant", content))

    def on_run_start(self, **kwargs):
        pass

    def on_run_end(self, **kwargs):
        pass


@pytest.fixture
def stub_base(monkeypatch, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    # OPENAI_API_BASE takes precedence in the OpenAI client and CI exports it,
    # so pin it to the stub too or requests escape to the real API.
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield base
    server.shutdown()


@pytest.mark.parametrize("route", ["openai_client", "custom_llm"])
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_user_message_is_persisted(stub_base, mode, route):
    db = _Recorder()
    if route == "openai_client":
        llm = dict(llm="gpt-4o-mini")
    else:  # litellm LLM class: must not write the user row twice
        llm = dict(llm="openai/local-model", base_url=stub_base, api_key="x")
    agent = Agent(name="p", instructions="hi", output="silent",
                  memory=MemoryConfig(db=db, user_id="u"), **llm)
    result = agent.chat("hi there") if mode == "sync" else asyncio.run(agent.achat("hi there"))
    assert result == "hello"
    assert db.rows.count(("user", "hi there")) == 1


@pytest.mark.parametrize("route", ["openai_client", "custom_llm"])
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_assistant_reply_is_persisted(stub_base, mode, route):
    db = _Recorder()
    if route == "openai_client":
        llm = dict(llm="gpt-4o-mini")
    else:
        llm = dict(llm="openai/local-model", base_url=stub_base, api_key="x")
    agent = Agent(name="p", instructions="hi", output="silent",
                  memory=MemoryConfig(db=db, user_id="u"), **llm)
    agent.chat("hi there") if mode == "sync" else asyncio.run(agent.achat("hi there"))
    assert db.rows.count(("assistant", "hello")) == 1
