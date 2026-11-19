"""Gateway request limits and probe output.

* Every request body is capped (shared ``limit_request_body``) before a
  handler buffers it, including ``/webhooks/{channel}``, which verifies its
  signature only after reading the body.
* ``/health`` without a credential returns only the status on a gateway
  that has an ``auth_token``; channel names and counters need the token.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")

from praisonaiagents.gateway.config import GatewayConfig
from praisonai_bot.gateway.server import WebSocketGateway

TOKEN = "request-limits-test-token-0123456789"


async def _build(monkeypatch, tmp_path, config, setup=None):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ALLOW_LOOPBACK_BYPASS", "false")
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.check_port_available", lambda *a: (True, None))
    lock = SimpleNamespace(acquire_lock=Mock(return_value=True), release_lock=Mock())
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.GatewayPIDLock", lambda **kw: lock)
    server = SimpleNamespace(serve=AsyncMock(), should_exit=False)

    def capture(cfg):
        server.app = cfg.app
        return server

    monkeypatch.setattr("uvicorn.Server", capture)
    gateway = WebSocketGateway(config=config)
    if setup:
        setup(gateway)
    await gateway.start()
    return server.app


def _client(app, peer="203.0.113.9"):
    transport = httpx.ASGITransport(app=app, client=(peer, 50000))
    return httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765")


def test_webhook_body_over_the_cap_is_refused_before_the_adapter(monkeypatch, tmp_path):
    seen = {}

    class Adapter:
        async def handle_shared_request(self, raw_body=None, headers=None, query=None):
            seen["bytes"] = len(raw_body)
            return 200, "ok"

    async def scenario():
        app = await _build(
            monkeypatch, tmp_path, GatewayConfig(auth_token=TOKEN),
            setup=lambda g: g._webhook_channels.__setitem__("telegram", Adapter()),
        )

        async def stream():  # chunked, no Content-Length
            chunk = b"A" * (1 << 20)
            for _ in range(30):  # 30 MB, over the 25 MB cap
                yield chunk

        async with _client(app) as c:
            big = await c.post("/webhooks/telegram", content=stream())
            small = await c.post("/webhooks/telegram", content=b"{}")
        return big.status_code, small.status_code

    big, small = asyncio.run(scenario())
    assert big == 413
    assert small == 200 and seen["bytes"] == 2


def test_health_without_a_token_returns_status_only(monkeypatch, tmp_path):
    class Bot:
        platform = "telegram"
        is_running = True

    async def scenario():
        config = GatewayConfig(host="0.0.0.0", auth_token=TOKEN, allowed_origins=["https://ops.example"])
        app = await _build(
            monkeypatch, tmp_path, config,
            setup=lambda g: g._channel_bots.__setitem__("support-telegram", Bot()),
        )
        async with _client(app) as c:
            anon = await c.get("/health")
            authed = await c.get("/health", headers={"Authorization": f"Bearer {TOKEN}"})
        return anon, authed

    anon, authed = asyncio.run(scenario())
    assert anon.status_code == 200
    assert set(anon.json()) == {"status"}
    assert "support-telegram" not in anon.text
    assert "support-telegram" in authed.text
