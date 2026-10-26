"""A valid HMAC signature authenticates a ``/hooks/<path>`` delivery (#6034).

Signed providers (GitHub, Stripe, Slack) cannot send a bearer token, so a hook
with only ``secret`` must not fall back to the gateway ``auth_token``. The real
Starlette app is built by ``WebSocketGateway.start()`` (server not served).
"""
import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")

from praisonaiagents.gateway import HookConfig
from praisonaiagents.gateway.config import GatewayConfig
from praisonai_bot.gateway.server import WebSocketGateway

SECRET = "gh-webhook-secret"
GATEWAY_TOKEN = "gw-operator-token"


async def _post_all(monkeypatch, tmp_path, hook, requests):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    # The durable hook idempotency store lives under ``Path.home()``.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("ALLOW_LOOPBACK_BYPASS", "false")
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", GATEWAY_TOKEN)
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.check_port_available", lambda *a: (True, None))
    lock = SimpleNamespace(acquire_lock=Mock(return_value=True), release_lock=Mock())
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.GatewayPIDLock", lambda **kw: lock)
    server = SimpleNamespace(serve=AsyncMock(), should_exit=False)

    def capture_server(config):
        server.app = config.app
        return server

    monkeypatch.setattr("uvicorn.Server", capture_server)
    gateway = WebSocketGateway(config=GatewayConfig(auth_token=GATEWAY_TOKEN))
    gateway.register_hook(hook)
    run = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(gateway, "_run_hook", run)
    await gateway.start()
    codes = []
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        for body, headers in requests:
            resp = await client.post("/hooks/github", content=body, headers=headers)
            codes.append(resp.status_code)
    return codes, run.await_count


def _run(monkeypatch, tmp_path, hook, requests):
    return asyncio.run(_post_all(monkeypatch, tmp_path, hook, requests))


def _delivery(n, secret=SECRET):
    body = json.dumps({"action": "opened", "issue": {"number": n}}).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Hub-Signature-256": sig, "X-GitHub-Event": "issues"}


def _hook(**kw):
    return HookConfig(path="github", agent="triage", idempotency_key="{issue.number}", **kw)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_signed_delivery_accepted_without_token(monkeypatch, tmp_path):
    codes, runs = _run(monkeypatch, tmp_path, _hook(secret=SECRET), [_delivery(1)])
    assert codes == [200]
    assert runs == 1


def test_bad_or_missing_signature_rejected(monkeypatch, tmp_path):
    body, headers = _delivery(2, secret="wrong")
    codes, runs = _run(monkeypatch, tmp_path, _hook(secret=SECRET), [
        (body, headers),
        (body, {}),
        # A valid gateway token does not stand in for a bad signature.
        (body, _bearer(GATEWAY_TOKEN)),
    ])
    assert codes == [401, 401, 401]
    assert runs == 0


def test_no_secret_still_requires_gateway_auth(monkeypatch, tmp_path):
    body, _ = _delivery(3)
    codes, runs = _run(monkeypatch, tmp_path, _hook(), [
        (body, {}),
        (body, _bearer(GATEWAY_TOKEN)),
    ])
    assert codes == [401, 200]
    assert runs == 1


def test_secret_and_auth_require_both(monkeypatch, tmp_path):
    body, headers = _delivery(4)
    _, bad_headers = _delivery(4, secret="wrong")
    codes, runs = _run(monkeypatch, tmp_path, _hook(secret=SECRET, auth="hook-bearer"), [
        (body, headers),
        (body, {**headers, **_bearer("wrong-bearer")}),
        (body, {**bad_headers, **_bearer("hook-bearer")}),
        (body, {**headers, **_bearer("hook-bearer")}),
    ])
    assert codes == [401, 403, 401, 200]
    assert runs == 1
