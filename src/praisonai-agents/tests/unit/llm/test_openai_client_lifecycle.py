"""Regression tests for #5858: sync bridge must not leave orphan aclose tasks."""

import asyncio
import gc
import json
import threading
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("openai")

from praisonaiagents.llm.openai_client import OpenAIClient
from praisonaiagents.utils.async_bridge import run_coroutine_from_any_context

_COMPLETION = json.dumps({
    "id": "x", "object": "chat.completion", "created": 0, "model": "m",
    "choices": [{"index": 0, "finish_reason": "stop",
                 "message": {"role": "assistant", "content": "hi"}}],
}).encode()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive so pooled connections stay open

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(_COMPLETION)))
        self.end_headers()
        self.wfile.write(_COMPLETION)

    def log_message(self, *args):
        pass


@pytest.fixture
def client():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield OpenAIClient(api_key="k", base_url=f"http://127.0.0.1:{server.server_port}/v1")
    finally:
        server.shutdown()
        server.server_close()


def test_sync_calls_across_loops_leave_no_orphan_aclose_task(client):
    errors = []

    async def call():
        asyncio.get_running_loop().set_exception_handler(
            lambda _loop, ctx: errors.append(ctx)
        )
        # Accessing async_client on a new loop drops the client bound to the
        # previous (closed) loop; collecting it must not schedule aclose here.
        async_client = client.async_client
        gc.collect()
        await asyncio.sleep(0.05)
        r = await async_client.chat.completions.create(
            model="m", messages=[{"role": "user", "content": "x"}]
        )
        return r.choices[0].message.content

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        for _ in range(3):
            assert run_coroutine_from_any_context(call()) == "hi"
            gc.collect()
    assert errors == []


def test_sync_close_does_not_create_unawaited_coroutine(client):
    async def touch():
        return client.async_client

    run_coroutine_from_any_context(touch())
    # Record rather than raise: an unawaited-coroutine warning is emitted from
    # the coroutine finaliser, where "error" is routed to sys.unraisablehook
    # and would not fail the test.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", RuntimeWarning)
        client.close()
        gc.collect()
    assert not [w for w in caught if "never awaited" in str(w.message)]
    assert client._async_client is None
