"""Loopback servers refuse cross-site requests (foreign Origin, rebound Host)."""

import asyncio
from unittest.mock import patch

import pytest

from praisonaiagents.agent.origin_guard import guard_loopback_requests, is_loopback_request


@pytest.mark.parametrize("headers, ok", [
    ({"host": "127.0.0.1:8000"}, True),
    ({"host": "localhost:8000", "origin": "http://localhost:3000"}, True),
    ({"host": "[::1]:8000", "origin": "http://[::1]:8000"}, True),
    ({"host": "app.localhost"}, True),
    ({"host": "foreign.example:8000"}, False),                       # DNS rebinding
    ({"host": "127.0.0.1:8000", "origin": "https://foreign.example"}, False),  # cross-site
    ({"host": "127.0.0.1:8000", "origin": "null"}, False),
    ({}, False),
])
def test_loopback_request_classification(headers, ok):
    assert is_loopback_request(headers) is ok


async def _ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _status(app, headers):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"]


def test_guard_refuses_cross_site_on_loopback_bind():
    app = guard_loopback_requests(_ok, "127.0.0.1")
    assert _status(app, {"host": "127.0.0.1:1"}) == 200
    assert _status(app, {"host": "foreign.example:1"}) == 403
    assert _status(app, {"host": "127.0.0.1:1", "origin": "https://foreign.example"}) == 403


def test_guard_leaves_non_loopback_binds_to_token_auth():
    assert guard_loopback_requests(_ok, "0.0.0.0") is _ok


def test_mcp_sse_default_server_refuses_rebound_host(monkeypatch):
    pytest.importorskip("mcp.server.sse")
    from starlette.testclient import TestClient

    from praisonaiagents.mcp.mcp_server import ToolsMCPServer

    for var in ("MCP_SSE_AUTH_TOKEN", "MCP_AUTH_TOKEN", "MCP_SSE_ALLOWED_ORIGINS"):
        monkeypatch.delenv(var, raising=False)

    def ping(text: str) -> str:
        """Echo."""
        return text

    with patch("uvicorn.run") as run:
        ToolsMCPServer(name="t", tools=[ping]).run_sse()
    app, host = run.call_args.args[0], run.call_args.kwargs["host"]
    assert host == "127.0.0.1"
    client = TestClient(app)
    hdrs = {"Host": "foreign.example:8080", "Origin": "http://foreign.example:8080"}
    assert client.post("/messages/?session_id=x", json={}, headers=hdrs).status_code == 403
    local = client.post("/messages/?session_id=x", json={}, headers={"Host": "127.0.0.1:8080"})
    assert local.status_code != 403


def test_unknown_bind_checks_origin_only():
    app = guard_loopback_requests(_ok, None)
    assert _status(app, {"host": "testserver"}) == 200
    assert _status(app, {"host": "testserver", "origin": "https://foreign.example"}) == 403
    assert _status(app, {"host": "testserver", "origin": "http://localhost:3000"}) == 200
