"""Signature-only auth for ``/hooks/<path>`` is an explicit opt-in (#6034).

By default a signed hook still needs the gateway ``auth_token`` (or its own
``auth``), and the signature is checked on top. ``signature_only=True`` lets a
replay-bounded signature (``hmac_timestamped``/``structured`` with a tolerance)
authenticate on its own; any other combination is rejected at load time. The
real Starlette app is built by ``WebSocketGateway.start()`` (server not served).
"""
import asyncio
import hashlib
import hmac
import json
import time
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


def _timestamped(n, secret=SECRET, ts=None):
    body = json.dumps({"action": "opened", "issue": {"number": n}}).encode()
    ts = str(int(time.time()) if ts is None else ts)
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"X-Signature": sig, "X-Timestamp": ts}


def _hook(**kw):
    return HookConfig(path="github", agent="triage", idempotency_key="{issue.number}", **kw)


def _ts_hook(**kw):
    return _hook(
        secret=SECRET, signature_header="X-Signature", timestamp_header="X-Timestamp",
        signature_scheme="hmac_timestamped", **kw,
    )


def _opt_in(**kw):
    return _ts_hook(signature_only=True, **kw)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_upgraded_timestamped_hook_still_requires_gateway_token(monkeypatch, tmp_path):
    # Default is unchanged from main: no opt-in means the token is required.
    body, headers = _timestamped(9)
    codes, runs = _run(monkeypatch, tmp_path, _ts_hook(), [
        (body, headers),
        (body, {**headers, **_bearer(GATEWAY_TOKEN)}),
    ])
    assert codes == [401, 200]
    assert runs == 1


def test_signature_only_opt_in_accepted_without_token(monkeypatch, tmp_path):
    codes, runs = _run(monkeypatch, tmp_path, _opt_in(), [_timestamped(1)])
    assert codes == [200]
    assert runs == 1


def test_signature_only_from_dict(monkeypatch, tmp_path):
    hook = HookConfig.from_dict({
        "path": "github", "agent": "triage", "idempotency_key": "{issue.number}",
        "secret": SECRET, "signature_header": "X-Signature",
        "timestamp_header": "X-Timestamp", "signature_scheme": "hmac_timestamped",
        "signature_only": True,
    })
    assert hook.signature_only is True
    assert "signature_only" not in hook.metadata
    codes, runs = _run(monkeypatch, tmp_path, hook, [_timestamped(11)])
    assert codes == [200]
    assert runs == 1


@pytest.mark.parametrize("kw", [
    {"secret": SECRET},  # body-only hmac_hex
    {"secret": SECRET, "signature_scheme": "hmac_base64"},
    {"secret": SECRET, "signature_scheme": "structured", "signature_tolerance_seconds": 0},
    {"signature_scheme": "structured"},  # no secret
])
def test_signature_only_rejected_without_replay_bound(kw):
    with pytest.raises(ValueError, match="signature_only"):
        _hook(signature_only=True, **kw)
    with pytest.raises(ValueError, match="signature_only"):
        HookConfig.from_dict({"path": "github", "signature_only": True, **kw})


def test_stale_timestamped_delivery_rejected(monkeypatch, tmp_path):
    # A captured delivery replayed outside the tolerance window is refused.
    stale = _timestamped(6, ts=int(time.time()) - 3600)
    codes, runs = _run(monkeypatch, tmp_path, _opt_in(), [stale])
    assert codes == [401]
    assert runs == 0


def test_body_only_signature_still_requires_gateway_token(monkeypatch, tmp_path):
    body, headers = _delivery(7)
    codes, runs = _run(monkeypatch, tmp_path, _hook(secret=SECRET), [
        (body, headers),
        (body, {**headers, **_bearer(GATEWAY_TOKEN)}),
    ])
    assert codes == [401, 200]
    assert runs == 1


@pytest.mark.parametrize("make_hook", [_ts_hook, _opt_in])
def test_bad_or_missing_signature_rejected(monkeypatch, tmp_path, make_hook):
    body, headers = _timestamped(2, secret="wrong")
    codes, runs = _run(monkeypatch, tmp_path, make_hook(), [
        (body, headers),
        (body, {}),
        # A valid gateway token does not stand in for a bad signature.
        (body, {**headers, **_bearer(GATEWAY_TOKEN)}),
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
    body, headers = _timestamped(4)
    _, bad_headers = _timestamped(4, secret="wrong")
    codes, runs = _run(monkeypatch, tmp_path, _opt_in(auth="hook-bearer"), [
        (body, headers),
        (body, {**headers, **_bearer("wrong-bearer")}),
        (body, {**bad_headers, **_bearer("hook-bearer")}),
        (body, {**headers, **_bearer("hook-bearer")}),
    ])
    assert codes == [401, 403, 401, 200]
    assert runs == 1


def test_oversized_body_rejected_before_signature_check(monkeypatch, tmp_path):
    # A signature-only hook reads the body before any credential is proven, so
    # the read is bounded: an oversized delivery gets 413 and never runs.
    monkeypatch.setattr("praisonai_bot.gateway.server._HOOK_MAX_BODY_BYTES", 64)
    big, big_headers = _timestamped(10**80)
    small, small_headers = _timestamped(5)
    assert len(big) > 64 >= len(small)
    codes, runs = _run(monkeypatch, tmp_path, _opt_in(), [
        (big, big_headers),
        (small, small_headers),
    ])
    assert codes == [413, 200]
    assert runs == 1


def test_unsigned_request_rejected_before_body_read(monkeypatch, tmp_path):
    # With no signature header a signature-only hook cannot authenticate, so
    # the request is refused (401) before the body is buffered: never 413.
    monkeypatch.setattr("praisonai_bot.gateway.server._HOOK_MAX_BODY_BYTES", 64)
    big, headers = _timestamped(10**80)
    assert len(big) > 64
    ts = {"X-Timestamp": headers["X-Timestamp"]}
    codes, runs = _run(monkeypatch, tmp_path, _opt_in(), [
        (big, ts),
        (big, {**ts, **_bearer(GATEWAY_TOKEN)}),
    ])
    assert codes == [401, 401]
    assert runs == 0
