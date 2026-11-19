"""Network servers default to loopback; a non-loopback bind is never keyless."""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.agent import launch_security


@pytest.fixture(autouse=True)
def _clean_tokens(monkeypatch):
    monkeypatch.delenv("PRAISONAI_LAUNCH_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_SSE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(launch_security, "_GENERATED_TOKEN", None)


def _a2a():
    pytest.importorskip("fastapi")
    from praisonaiagents.ui.a2a import A2A

    agent = MagicMock()
    agent.name = "a"
    agent.role = "r"
    return A2A(agent=agent)


def test_a2a_serve_defaults_to_loopback_without_token():
    a2a = _a2a()
    with patch("uvicorn.run") as run:
        a2a.serve()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert a2a.auth_token is None


def test_a2a_serve_public_host_requires_token():
    a2a = _a2a()  # skips when fastapi is not installed
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    a2a.get_router()  # a router cached before serve() must not stay open
    with patch("uvicorn.run") as run:
        a2a.serve(host="0.0.0.0")
    assert run.call_args.kwargs["host"] == "0.0.0.0"
    assert a2a.auth_token

    app = FastAPI()
    app.include_router(a2a.get_router())
    client = TestClient(app)
    body = {"jsonrpc": "2.0", "id": 1, "method": "tasks/list", "params": {}}
    assert client.post("/a2a", json=body).status_code == 401
    ok = client.post("/a2a", json=body, headers={"Authorization": f"Bearer {a2a.auth_token}"})
    assert ok.status_code == 200


def test_a2a_serve_public_host_keeps_explicit_token():
    a2a = _a2a()
    a2a.auth_token = "mine"
    with patch("uvicorn.run"):
        a2a.serve(host="0.0.0.0")
    assert a2a.auth_token == "mine"


def test_server_registry_defaults_to_loopback():
    from praisonaiagents.agent.server_registry import _AgentServerRegistry

    default = inspect.signature(_AgentServerRegistry.start_server_if_needed).parameters["host"].default
    assert default == "127.0.0.1"


def test_launch_tools_mcp_server_leaves_host_to_security_config():
    from praisonaiagents.mcp import mcp_server

    with patch.object(mcp_server.ToolsMCPServer, "run_sse") as run_sse:
        mcp_server.launch_tools_mcp_server(tools=[lambda q: q], transport="sse")
    assert run_sse.call_args.kwargs["host"] is None


def _run_sse(host):
    pytest.importorskip("mcp")
    from praisonaiagents.mcp.mcp_server import ToolsMCPServer

    server = ToolsMCPServer(name="t")
    with patch("uvicorn.run") as run:
        server.run_sse(host=host, port=8099)
    return run.call_args


def test_mcp_sse_loopback_stays_keyless(monkeypatch):
    call = _run_sse(None)
    assert call.kwargs["host"] == "127.0.0.1"
    assert "MCP_SSE_AUTH_TOKEN" not in __import__("os").environ


def test_mcp_sse_public_host_requires_token():
    import os

    from starlette.testclient import TestClient

    call = _run_sse("0.0.0.0")
    token = os.environ.get("MCP_SSE_AUTH_TOKEN")
    assert token
    client = TestClient(call.args[0])
    assert client.get("/messages/", headers={"Origin": "http://localhost"}).status_code == 401
