"""A caller-supplied ``X-Operator-Id`` must not grant approval custody (#6428)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")

from praisonaiagents.gateway.config import GatewayConfig, MultiChannelGatewayConfig
from praisonai_bot.gateway.exec_approval import ExecApprovalManager, Resolution
from praisonai_bot.gateway.server import WebSocketGateway


TOKEN = "test-operator-identity-token"


def _resolve_as_alice(monkeypatch, tmp_path, gateway_yaml, extra_headers=None):
    """POST a resolve claiming ``X-Operator-Id: alice``; return (status, resolved)."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setenv("ALLOW_LOOPBACK_BYPASS", "false")
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", TOKEN)
    manager = ExecApprovalManager(durable=False)
    monkeypatch.setattr("praisonai_bot.gateway.exec_approval.get_exec_approval_manager", lambda: manager)
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.check_port_available", lambda *a: (True, None))
    lock = SimpleNamespace(acquire_lock=Mock(return_value=True), release_lock=Mock())
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.GatewayPIDLock", lambda **kw: lock)
    server = SimpleNamespace(serve=AsyncMock(), should_exit=False)

    def capture_server(config):
        config.load()  # the app as uvicorn serves it, middleware included
        server.app = config.loaded_app
        return server

    monkeypatch.setattr("uvicorn.Server", capture_server)

    async def scenario():
        gateway = WebSocketGateway(config=GatewayConfig(auth_token=TOKEN))
        await gateway.start()
        gateway._loaded_config = {"gateway": gateway_yaml}
        request_id, future = await manager.register(
            tool_name="send_report", arguments={"report": "x"},
            agent_name="planner", authorized_reviewers={"operator:alice"},
        )
        headers = {"Authorization": f"Bearer {TOKEN}", "X-Operator-Id": "alice"}
        headers.update(extra_headers or {})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url="http://gateway",
        ) as client:
            response = await client.post(
                "/api/approval/resolve", headers=headers,
                json={"request_id": request_id, "approved": True},
            )
        for _ in range(20):  # let a successful resolve land on the future
            if future.done():
                break
            await asyncio.sleep(0.01)
        status, resolved = response.status_code, future.done()
        if not resolved:
            manager.resolve(request_id, Resolution(approved=False, resolver="operator:alice"))
        decision = await asyncio.wait_for(future, 5)
        assert decision.approved is resolved
        return status, resolved

    return asyncio.run(scenario())


def test_spoofed_operator_header_cannot_resolve_other_reviewers_request(monkeypatch, tmp_path):
    assert _resolve_as_alice(monkeypatch, tmp_path, {}) == (404, False)


def test_trusted_proxy_alone_does_not_enable_header(monkeypatch, tmp_path):
    cfg = {"trusted_proxies": ["127.0.0.1"]}
    assert _resolve_as_alice(monkeypatch, tmp_path, cfg) == (404, False)


def test_opt_in_header_ignored_from_untrusted_peer(monkeypatch, tmp_path):
    cfg = {"trust_operator_header": True, "trusted_proxies": ["10.0.0.1"]}
    assert _resolve_as_alice(monkeypatch, tmp_path, cfg) == (404, False)


def test_opt_in_header_honoured_from_trusted_proxy(monkeypatch, tmp_path):
    # httpx's ASGI transport presents the socket peer as 127.0.0.1.
    cfg = {"trust_operator_header": True, "trusted_proxies": ["127.0.0.1"]}
    assert _resolve_as_alice(monkeypatch, tmp_path, cfg) == (200, True)


def test_forged_forwarded_for_cannot_impersonate_trusted_proxy(monkeypatch, tmp_path):
    # A loopback caller claims to be the trusted proxy via X-Forwarded-For.
    cfg = {"trust_operator_header": True, "trusted_proxies": ["10.0.0.1"]}
    forged = {"X-Forwarded-For": "10.0.0.1"}
    assert _resolve_as_alice(monkeypatch, tmp_path, cfg, forged) == (404, False)


def test_yaml_with_trust_keys_validates_and_drives_resolver(monkeypatch, tmp_path):
    """Both keys load through the real loader and gate the header end to end."""
    cfg_path = tmp_path / "gateway.yaml"
    cfg_path.write_text(
        "gateway:\n"
        "  trust_operator_header: true\n"
        "  trusted_proxies: ['127.0.0.1']\n"
        "agents:\n  a: {instructions: hi}\n"
        "channels:\n  telegram: {token: t}\n"
    )
    loaded = WebSocketGateway.load_gateway_config(str(cfg_path))
    gw = loaded["gateway"]
    assert gw["trust_operator_header"] is True
    assert gw["trusted_proxies"] == ["127.0.0.1"]

    core = MultiChannelGatewayConfig.from_dict(loaded, strict=True).gateway
    assert core.trust_operator_header is True
    assert core.to_dict()["trust_operator_header"] is True
    assert GatewayConfig().trust_operator_header is False

    assert _resolve_as_alice(monkeypatch, tmp_path, gw) == (200, True)
    untrusted = dict(gw, trusted_proxies=["10.0.0.1"])
    assert _resolve_as_alice(monkeypatch, tmp_path, untrusted) == (404, False)
