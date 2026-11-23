"""G-05: ``return_token_usage=True`` must report real usage on the sync Responses route.

The sync Responses API branch of ``LLM.get_response`` updated the token
collector but never recorded the response it returned usage from, so callers
got ``TokenUsage(0, 0, 0)``; ``get_response_async`` returned the real counts.
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
    "usage": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10,
              "input_tokens_details": {"cached_tokens": 5}},
    "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        if req.get("stream"):
            events = [
                {"type": "response.output_text.delta", "item_id": "msg_1", "output_index": 0,
                 "content_index": 0, "delta": "hello", "sequence_number": 1},
                {"type": "response.completed", "sequence_number": 2, "response": _RESPONSE},
            ]
            body = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
            ctype = "text/event-stream"
        else:
            body, ctype = json.dumps(_RESPONSE).encode(), "application/json"
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def base(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    # Route via the env var so this test does not depend on the G-01 fix.
    monkeypatch.setenv("OPENAI_BASE_URL", url)
    monkeypatch.setenv("OPENAI_API_BASE", url)
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_responses_route_returns_token_usage(base, mode, stream):
    llm = LLM(model="gpt-4o-mini", api_key="x", api_base=base)
    assert llm._supports_responses_api()
    kwargs = dict(prompt="hi", return_token_usage=True, verbose=False, stream=stream)
    if mode == "sync":
        text, usage = llm.get_response(**kwargs)
    else:
        text, usage = asyncio.run(llm.get_response_async(**kwargs))
    assert text == "hello"
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (7, 3, 10)
    assert usage.cached_tokens == 5
