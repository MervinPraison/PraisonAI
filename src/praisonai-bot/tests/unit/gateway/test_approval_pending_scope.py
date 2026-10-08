"""Approval arguments must not be exposed to operators without approval scope."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

pytest.importorskip("starlette")
pytest.importorskip("uvicorn")

from praisonaiagents.gateway.config import GatewayConfig
from praisonai_bot.gateway.exec_approval import ExecApprovalManager, Resolution
from praisonai_bot.gateway.server import WebSocketGateway


TOKEN = "test-approval-inspection-token"


async def build_app(monkeypatch, tmp_path, scopes):
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
        server.app = config.app
        return server

    monkeypatch.setattr("uvicorn.Server", capture_server)
    config = GatewayConfig(auth_token=TOKEN, auth_scopes=None if scopes is None else {TOKEN: scopes})
    gateway = WebSocketGateway(config=config)
    await gateway.start()
    return server.app, manager


@pytest.mark.parametrize("scopes, expected", [
    (["read"], 403), (["write"], 403), ([], 403),
    (["approvals"], 200), (["admin"], 200), (None, 200),
])
def test_pending_queue_requires_approval_scope(monkeypatch, tmp_path, scopes, expected):
    async def scenario():
        app, manager = await build_app(monkeypatch, tmp_path, scopes)
        request_id, future = await manager.register(
            tool_name="send_report", arguments={"report": "private planning notes"}, agent_name="planner",
        )
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            response = await client.get("/api/approval/pending", headers={"Authorization": f"Bearer {TOKEN}"})
        assert response.status_code == expected
        if expected == 403:
            assert response.json() == {"error": "insufficient scope", "required_scope": "approvals"}
            assert "private planning notes" not in response.text
            assert "send_report" not in response.text
        else:
            assert response.json()["pending"][0]["request_id"] == request_id
        assert not future.done()
        manager.resolve(request_id, Resolution(approved=False, reason="cleanup"))
        await future

    asyncio.run(scenario())


def test_denied_polling_does_not_exhaust_approval_budget(monkeypatch, tmp_path):
    async def scenario():
        app, _ = await build_app(monkeypatch, tmp_path, ["read"])
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            for _ in range(12):
                response = await client.get("/api/approval/pending", headers=headers)
                assert response.status_code == 403

    asyncio.run(scenario())


@pytest.mark.skipif(os.getenv("PRAISONAI_LIVE_TESTS") != "1", reason="Opt-in real LLM test")
def test_generated_report_requires_approval_scope(monkeypatch, tmp_path):
    from praisonaiagents import Agent

    agent = Agent(
        name="report-planner", instructions="Write a short report for operator review.",
        model={"model": os.getenv("PRAISONAI_TEST_MODEL", "gpt-4o-mini"), "max_tokens": 96},
        reflection=False, rules=False, output="silent",
    )
    report = agent.start("Write one sentence about a proposed deployment.")
    print(report)
    assert isinstance(report, str) and report.strip()

    async def scenario():
        app, manager = await build_app(monkeypatch, tmp_path, ["read"])
        request_id, future = await manager.register(
            tool_name="send_report", arguments={"report": report}, agent_name=agent.name,
        )
        headers = {"Authorization": f"Bearer {TOKEN}"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gateway") as client:
            denied = await client.get("/api/approval/pending", headers=headers)
            assert denied.status_code == 403
            assert report not in denied.text
        manager.resolve(request_id, Resolution(approved=False, reason="cleanup"))
        await future

    asyncio.run(scenario())
