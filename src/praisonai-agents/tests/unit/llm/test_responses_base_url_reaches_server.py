"""G-01: ``base_url=`` must reach the server on the Responses API route.

Model names such as ``gpt-4o-mini`` take the ``litellm.responses()`` route.
``litellm.responses()`` honours ``api_base`` and ignores ``base_url``, so
``Agent(llm="gpt-4o-mini", base_url=<proxy>, api_key=<its key>)`` sent the
request, with that key, to api.openai.com instead of the proxy.
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from praisonaiagents.llm.llm import LLM

_RESPONSE = {
    "id": "resp_1", "object": "response", "created_at": 0, "status": "completed",
    "model": "gpt-4o-mini",
    "output": [{"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                "content": [{"type": "output_text", "text": "hello", "annotations": []}]}],
    "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
    "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
}
_CHAT = {
    "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-4o-mini",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
}


@pytest.fixture
def stub(monkeypatch):
    for var in ("OPENAI_BASE_URL", "OPENAI_API_BASE"):
        monkeypatch.delenv(var, raising=False)
    hits = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("content-length", 0)))
            hits.append(self.path)
            body = json.dumps(_RESPONSE if self.path.endswith("/responses") else _CHAT).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1", hits
    server.shutdown()
    server.server_close()


def test_responses_params_carry_api_base():
    params = LLM(model="gpt-4o-mini", base_url="http://proxy.local/v1")._build_responses_params(
        [{"role": "user", "content": "hi"}]
    )
    assert params["api_base"] == "http://proxy.local/v1"


def test_per_call_base_url_wins_and_explicit_api_base_is_kept():
    llm = LLM(model="gpt-4o-mini", base_url="http://a.local/v1")
    msgs = [{"role": "user", "content": "hi"}]
    assert llm._build_responses_params(msgs, base_url="http://b.local/v1")["api_base"] == "http://b.local/v1"
    assert LLM(model="gpt-4o-mini")._build_responses_params(
        msgs, base_url="http://b.local/v1")["api_base"] == "http://b.local/v1"
    assert llm._build_responses_params(msgs, api_base="http://c.local/v1")["api_base"] == "http://c.local/v1"


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_responses_route_sends_to_base_url(stub, mode):
    base, hits = stub
    llm = LLM(model="gpt-4o-mini", base_url=base, api_key="x")
    assert llm._supports_responses_api()
    kwargs = dict(prompt="hi", verbose=False, stream=False)
    if mode == "sync":
        result = llm.get_response(**kwargs)
    else:
        result = asyncio.run(llm.get_response_async(**kwargs))
    assert hits == ["/v1/responses"]
    assert result == "hello"
