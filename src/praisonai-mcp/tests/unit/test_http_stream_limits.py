"""MCP HTTP-stream: body size cap and the shared bind guard."""

from unittest.mock import patch

import pytest

pytest.importorskip("starlette")
from starlette.testclient import TestClient

from praisonai_mcp.mcp_server.server import MCPServer
from praisonai_mcp.mcp_server.transports.http_stream import HTTPStreamTransport


def _served_app():
    transport = HTTPStreamTransport(MCPServer(name="t"), host="127.0.0.1", port=18999)
    with patch("uvicorn.run") as run:
        transport.run()
    return run.call_args.args[0]


def test_oversize_post_is_refused_with_413(monkeypatch):
    import praisonaiagents.agent.request_limits as limits

    monkeypatch.setattr(limits, "DEFAULT_MAX_BODY_BYTES", 1024)
    client = TestClient(_served_app())
    resp = client.post("/mcp", content=b'"' + b"A" * 4096 + b'"',
                       headers={"content-type": "application/json"})
    assert resp.status_code == 413


def test_small_post_still_reaches_the_endpoint():
    client = TestClient(_served_app())
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status_code != 413


def test_public_bind_goes_through_shared_guard():
    from praisonaiagents.agent import launch_security

    with patch.object(launch_security, "require_bind_token",
                      wraps=launch_security.require_bind_token) as guard:
        with pytest.raises(ValueError, match="api_key"):
            HTTPStreamTransport(MCPServer(name="t"), host="0.0.0.0", port=18999)
    guard.assert_called_once()
