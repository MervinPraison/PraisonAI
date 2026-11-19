"""Every gateway route sits behind one guard: Origin, credential, operator scope.

The test builds the real Starlette app (HTTP API and MCP enabled, one hook
registered) and walks ``app.routes``. A route that is not listed in
``ROUTE_POLICY`` fails the test, so a new route must be classified before it
can ship. For each guarded route it checks that:

* no credential -> 401/403;
* a token that lacks the route's scope -> 403 ``insufficient scope``;
* a page on another site cannot use the loopback no-token mode (with or
  without ``auth_token`` set) -> 403.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")

from praisonaiagents.gateway.config import ApiConfig, GatewayConfig
from praisonai_bot.gateway.exec_approval import ExecApprovalManager
from praisonai_bot.gateway.origin_check import check_origin
from praisonai_bot.gateway.server import WebSocketGateway, _should_bypass_loopback_auth

TOKEN = "route-guard-test-token-0123456789"
FOREIGN = "https://foreign.example"

# (path, method) -> required operator scope, "auth" (any valid credential),
# or "public" (no gateway credential: probes, login, signed channel webhooks).
ROUTE_POLICY = {
    ("/", "GET"): "public",
    ("/health", "GET"): "public",
    ("/ready", "GET"): "public",
    ("/live", "GET"): "public",
    ("/webhooks/{channel}", "GET"): "public",
    ("/webhooks/{channel}", "POST"): "public",
    ("/hooks/{path:path}", "POST"): "auth",
    ("/info", "GET"): "auth",
    ("/metrics", "GET"): "read",
    ("/api/approval/pending", "GET"): "approvals",
    ("/api/approval/resolve", "POST"): "approvals",
    ("/api/approval/allow-list", "GET"): "approvals",
    ("/api/approval/allow-list", "POST"): "approvals",
    ("/api/approval/allow-list", "DELETE"): "approvals",
    ("/api/pairing/pending", "GET"): "pairing",
    ("/api/pairing/approve", "POST"): "pairing",
    ("/api/pairing/revoke", "POST"): "pairing",
    ("/api/channels/{name}/pause", "POST"): "admin",
    ("/api/channels/{name}/resume", "POST"): "admin",
    ("/api/channels/{name}/reconnect", "POST"): "admin",
    ("/v1/chat/completions", "POST"): "write",
    ("/v1/responses", "POST"): "write",
    ("/v1/responses/{id}", "GET"): "read",
    ("/v1/responses/{id}/cancel", "POST"): "write",
    ("/v1/models", "GET"): "read",
    ("/mcp", "POST"): "write",
    ("/ws", "WS"): "auth",
}

_FILL = {"{channel}": "telegram", "{path:path}": "ping", "{name}": "telegram", "{id}": "r1"}


def _concrete(path):
    for k, v in _FILL.items():
        path = path.replace(k, v)
    return path


async def _build_app(monkeypatch, tmp_path, *, auth_token=TOKEN, scopes=None, loopback_env="false"):
    # A gateway with no auth_token generates one and saves it to
    # ~/.praisonai/.env: keep HOME and PRAISONAI_HOME inside tmp_path.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    if loopback_env is None:
        monkeypatch.delenv("ALLOW_LOOPBACK_BYPASS", raising=False)
    else:
        monkeypatch.setenv("ALLOW_LOOPBACK_BYPASS", loopback_env)
    manager = ExecApprovalManager(durable=False)
    monkeypatch.setattr("praisonai_bot.gateway.exec_approval.get_exec_approval_manager", lambda: manager)
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.check_port_available", lambda *a: (True, None))
    lock = SimpleNamespace(acquire_lock=Mock(return_value=True), release_lock=Mock())
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.GatewayPIDLock", lambda **kw: lock)
    server = SimpleNamespace(serve=AsyncMock(), should_exit=False)

    def capture(config):
        server.app = config.app
        return server

    monkeypatch.setattr("uvicorn.Server", capture)
    config = GatewayConfig(
        auth_token=auth_token,
        auth_scopes=scopes,
        api=ApiConfig(openai=True, mcp=True),
    )
    gateway = WebSocketGateway(config=config)
    gateway.register_hook(path="ping", message="ping")
    await gateway.start()
    return server.app


def _routes(app):
    for route in app.routes:
        if type(route).__name__ == "WebSocketRoute":
            yield route.path, "WS"
            continue
        for method in sorted(route.methods - {"HEAD"}):
            yield route.path, method


def _guarded():
    return [(p, m) for (p, m), s in ROUTE_POLICY.items() if s != "public" and m != "WS"]


async def _call(app, path, method, headers):
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as c:
        return await c.request(method, _concrete(path), headers=headers, content=b"{}")


def test_every_route_is_classified(monkeypatch, tmp_path):
    app = asyncio.run(_build_app(monkeypatch, tmp_path))
    unclassified = sorted(set(_routes(app)) - set(ROUTE_POLICY))
    assert not unclassified, f"classify these gateway routes in ROUTE_POLICY: {unclassified}"


def test_no_credential_is_refused(monkeypatch, tmp_path):
    async def scenario():
        app = await _build_app(monkeypatch, tmp_path)
        return {(p, m): (await _call(app, p, m, {})).status_code for p, m in _guarded()}

    open_routes = {k: v for k, v in asyncio.run(scenario()).items() if v not in (401, 403)}
    assert not open_routes


def test_token_without_route_scope_is_refused(monkeypatch, tmp_path):
    # The token authenticates but holds no scopes, so every scoped route must
    # answer 403 "insufficient scope" before its handler runs.
    async def scenario():
        app = await _build_app(monkeypatch, tmp_path, scopes={TOKEN: []})
        auth = {"Authorization": f"Bearer {TOKEN}"}
        return {
            (p, m): await _call(app, p, m, auth)
            for p, m in _guarded()
            if ROUTE_POLICY[(p, m)] != "auth"
        }

    leaked = {
        k: r.status_code
        for k, r in asyncio.run(scenario()).items()
        if r.status_code != 403 or r.json().get("error") != "insufficient scope"
    }
    assert not leaked


@pytest.mark.parametrize("auth_token", [TOKEN, ""])
def test_cross_site_page_cannot_use_loopback_mode(monkeypatch, tmp_path, auth_token):
    async def scenario():
        app = await _build_app(monkeypatch, tmp_path, auth_token=auth_token, loopback_env=None)
        headers = {"Origin": FOREIGN, "Content-Type": "text/plain"}
        return {(p, m): (await _call(app, p, m, headers)).status_code for p, m in _guarded()}

    reached = {k: v for k, v in asyncio.run(scenario()).items() if v != 403}
    assert not reached


def test_local_page_keeps_loopback_mode(monkeypatch, tmp_path):
    async def scenario():
        app = await _build_app(monkeypatch, tmp_path, loopback_env=None)
        return await _call(app, "/api/approval/pending", "GET", {"Origin": "http://127.0.0.1:8765"})

    assert asyncio.run(scenario()).status_code == 200


def test_websocket_origin_policy_on_loopback():
    assert check_origin(FOREIGN, [], "127.0.0.1") is False
    assert check_origin("null", [], "127.0.0.1") is False
    assert check_origin(None, [], "127.0.0.1") is True
    assert check_origin("http://localhost:3000", [], "127.0.0.1") is True
    assert check_origin("http://[::1]:8765", [], "::1") is True
    assert check_origin("https://ui.example.com", ["https://ui.example.com"], "127.0.0.1") is True


def test_loopback_mode_needs_a_local_origin():
    assert _should_bypass_loopback_auth("127.0.0.1", "127.0.0.1", {"origin": FOREIGN}) is False
    assert _should_bypass_loopback_auth(
        "127.0.0.1", "127.0.0.1", {"origin": "http://localhost:8765"}
    ) is True
    assert _should_bypass_loopback_auth("127.0.0.1", "127.0.0.1", {}) is True


def test_websocket_refuses_cross_site_page_on_loopback(monkeypatch, tmp_path):
    from starlette.testclient import TestClient

    app = asyncio.run(_build_app(monkeypatch, tmp_path, auth_token="", loopback_env=None))
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        with client.websocket_connect("/ws", headers={"origin": FOREIGN}) as ws:
            assert ws.receive_json()["code"] == "origin_not_allowed"


def test_dns_rebound_host_does_not_get_loopback_mode(monkeypatch, tmp_path):
    """A page on foreign.example that resolves to 127.0.0.1 sends Host: foreign.example."""
    async def scenario():
        app = await _build_app(monkeypatch, tmp_path, loopback_env=None)
        return await _call(app, "/api/approval/pending", "GET", {"Host": "foreign.example:8765"})

    assert asyncio.run(scenario()).status_code == 401
    assert _should_bypass_loopback_auth("127.0.0.1", "127.0.0.1", {"host": "foreign.example"}) is False
    assert _should_bypass_loopback_auth("127.0.0.1", "127.0.0.1", {"host": "localhost:8765"}) is True
