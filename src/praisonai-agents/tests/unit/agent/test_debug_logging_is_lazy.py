"""G-10: per-turn debug logging must not format the history or tool payloads.

``logging.debug(f"... {messages}")`` built the whole conversation as a string
on every turn even with debug logging off (about 2 ms per turn at 4,000
messages). The same pattern formatted every raw tool result. Logging must
receive the payload as an argument so it is only formatted when emitted.
"""

import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents import Agent

PROMPT_MARK = "PROMPTMARK" * 500     # 5,000 chars in the user message
TOOL_MARK = "TOOLMARK" * 2_000       # 16,000 chars in the tool result


def _reply(messages, tools):
    if tools and not any(m.get("role") == "tool" for m in messages):
        msg = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": tools[0]["function"]["name"], "arguments": "{}"}}]}
        return msg, "tool_calls"
    return {"role": "assistant", "content": "done"}, "stop"


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        msg, finish = _reply(req.get("messages", []), req.get("tools"))
        body = json.dumps({
            "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub(monkeypatch, tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    # OPENAI_API_BASE takes precedence over OPENAI_BASE_URL (CI sets it), so pin both to the stub.
    monkeypatch.setenv("OPENAI_API_BASE", base)
    monkeypatch.setenv("OPENAI_BASE_URL", base)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    yield
    server.shutdown()


def payload_tool() -> dict:
    """Return a structured payload."""
    return {"data": TOOL_MARK}


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_debug_templates_do_not_embed_payloads(stub, monkeypatch, mode):
    templates = []
    real_debug = logging.Logger.debug

    # Patch the method, not the module function: it sees root-logger calls
    # (logging.debug delegates to it) and named-logger calls alike (X-08), at
    # call time and whatever the level, so eager formatting is still caught.
    def recording_debug(self, msg, *args, **kwargs):
        templates.append(str(msg))
        return real_debug(self, msg, *args, **kwargs)

    monkeypatch.setattr(logging.Logger, "debug", recording_debug)
    agent = Agent(name="t", instructions="hi", llm="gpt-4o-mini", tools=[payload_tool], output="silent")
    prompt = "go " + PROMPT_MARK
    result = agent.chat(prompt) if mode == "sync" else asyncio.run(agent.achat(prompt))
    assert result == "done"
    assert templates, "no debug calls recorded; the hook did not attach"
    eager = [t[:120] for t in templates if PROMPT_MARK in t or TOOL_MARK in t]
    assert eager == [], f"debug messages formatted eagerly: {eager}"
