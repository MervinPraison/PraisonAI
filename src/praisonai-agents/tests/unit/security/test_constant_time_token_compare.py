"""Server-side bearer/API token checks use a constant-time comparison.

Each server that guards network requests with a shared token must compare it
through ``hmac.compare_digest`` (via ``token_matches``) rather than ``==``.
The spy fixture records every ``hmac.compare_digest`` call so a site that
falls back to ``==`` fails here even though the accept/reject result is equal.
"""

import asyncio
import hmac
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

TOKEN = "sk-secret-token"


@pytest.fixture
def digest_calls(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    return calls


# ── shared helper ────────────────────────────────────────────────────────────

def test_token_matches_semantics():
    from praisonaiagents.agent.launch_security import token_matches

    assert token_matches(TOKEN, TOKEN)
    assert not token_matches("wrong", TOKEN)
    assert not token_matches(None, TOKEN)
    assert not token_matches("", TOKEN)
    assert not token_matches(TOKEN, None)
    assert not token_matches(None, None)
    # Non-ASCII input is compared as bytes instead of raising TypeError.
    assert not token_matches("tökén", TOKEN)
    assert token_matches("tökén", "tökén")


# ── AgentServer ──────────────────────────────────────────────────────────────

def _request(headers):
    return SimpleNamespace(headers=headers)


def test_agentserver_authorise_uses_constant_time(digest_calls):
    from praisonaiagents.server.server import AgentServer, ServerConfig

    server = AgentServer(config=ServerConfig(auth_token=TOKEN))
    assert server._authorise_request(_request({"Authorization": f"Bearer {TOKEN}"}))
    assert server._authorise_request(_request({"X-Auth-Token": TOKEN}))
    assert not server._authorise_request(_request({"Authorization": "Bearer nope"}))
    assert not server._authorise_request(_request({"X-Auth-Token": "tökén"}))
    assert not server._authorise_request(_request({}))
    assert digest_calls, "AgentServer token check did not use hmac.compare_digest"


def test_agentserver_without_token_stays_open():
    from praisonaiagents.server.server import AgentServer

    assert AgentServer()._authorise_request(_request({}))


# ── A2A ──────────────────────────────────────────────────────────────────────

def _a2a_client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")  # required by fastapi.testclient
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from praisonaiagents import Agent
    from praisonaiagents.ui.a2a import A2A

    a2a = A2A(agent=Agent(name="t", role="t", goal="t"), auth_token=TOKEN)
    a2a.agent.chat = MagicMock(return_value="ok")
    app = FastAPI()
    app.include_router(a2a.get_router())
    return TestClient(app)


_RPC = {
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {"message": {"messageId": "m1", "role": "user", "parts": [{"text": "hi"}]}},
}


def test_a2a_verify_auth_uses_constant_time(digest_calls):
    client = _a2a_client()
    assert client.post("/a2a", json=_RPC, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert digest_calls, "A2A token check did not use hmac.compare_digest"
    assert client.post("/a2a", json=_RPC, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200


# ── MCP SSE middleware ───────────────────────────────────────────────────────

def _sse_status(app, auth):
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    if auth is not None:
        scope["headers"].append((b"authorization", auth.encode("latin-1")))
    status = 500

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]

    asyncio.run(app(scope, receive, send))
    return status


def test_mcp_sse_middleware_uses_constant_time(monkeypatch, digest_calls):
    pytest.importorskip("starlette")
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from praisonaiagents.mcp.mcp_security import SecurityConfig, build_sse_security_app

    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("MCP_SSE_AUTH_TOKEN", TOKEN)
    app = Starlette(routes=[Route("/", lambda r: PlainTextResponse("ok"))])
    app = build_sse_security_app(app, SecurityConfig(require_auth=True, validate_origin=False))

    assert _sse_status(app, "Bearer nope") == 401
    assert digest_calls, "MCP SSE token check did not use hmac.compare_digest"
    assert _sse_status(app, None) == 401
    assert _sse_status(app, f"Bearer {TOKEN}") == 200
