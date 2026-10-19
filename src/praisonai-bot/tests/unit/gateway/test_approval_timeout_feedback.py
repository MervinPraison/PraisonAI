"""Timed-out approvals must tell the channel the action did NOT run (#5913)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from praisonaiagents.approval import ApprovalRequest
from praisonaiagents.approval.protocols import ApprovalDecision

from praisonai_bot.gateway.exec_approval import ExecApprovalManager
from praisonai_bot.gateway.gateway_approval import GatewayApprovalBackend

TIMEOUT = ApprovalDecision(
    approved=False, reason="Timed out", metadata={"timeout": True},
)
DENIED = ApprovalDecision(approved=False, reason="no", approver="42")


@pytest.mark.asyncio
async def test_gateway_timeout_sends_timed_out_notify():
    backend = GatewayApprovalBackend(
        ExecApprovalManager(durable=False), timeout=0.05,
        notify_url="http://example.invalid/hook",
    )
    sent = []

    async def fake_notify(request_id, request, status="pending"):
        sent.append(status)

    with patch.object(backend, "_notify", side_effect=fake_notify):
        decision = await backend.request_approval(
            ApprovalRequest(tool_name="rm", arguments={}, risk_level="high"),
        )
        await asyncio.sleep(0)  # let fire-and-forget tasks run

    assert decision.approved is False
    assert decision.approver == "gateway:timeout"
    assert sent == ["pending", "timed_out"]


@pytest.mark.asyncio
async def test_gateway_timeout_without_notify_url_is_silent():
    backend = GatewayApprovalBackend(ExecApprovalManager(durable=False), timeout=0.05)
    with patch.object(backend, "_notify") as notify:
        decision = await backend.request_approval(
            ApprovalRequest(tool_name="rm", arguments={}, risk_level="high"),
        )
    assert decision.approved is False
    notify.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("decision,expected,unexpected", [
    (TIMEOUT, "Timed out — not run", "Denied"),
    (DENIED, "Denied", "Timed out"),
])
async def test_telegram_card_shows_timeout(decision, expected, unexpected):
    from praisonai_bot.bots._telegram_approval import TelegramApproval

    bot = TelegramApproval(token="t", chat_id="1")
    bot._telegram_api = AsyncMock(return_value={"ok": True})
    req = ApprovalRequest(tool_name="rm", arguments={}, risk_level="high")
    await bot._update_message("1", 7, req, decision)

    method, payload = bot._telegram_api.call_args.args[:2]
    assert method == "editMessageText"
    assert "reply_markup" not in payload  # inert buttons are dropped
    assert expected in payload["text"]
    assert unexpected not in payload["text"].split("*Reason:*")[0]


@pytest.mark.asyncio
async def test_slack_card_shows_timeout():
    from praisonai_bot.bots._slack_approval import SlackApproval

    bot = SlackApproval(token="xoxb-t", channel="C1")
    bot._slack_api = AsyncMock(return_value={"ok": True})
    req = ApprovalRequest(tool_name="rm", arguments={}, risk_level="high")
    await bot._update_message("C1", "1.0", req, TIMEOUT)

    method, payload = bot._slack_api.call_args.args[:2]
    assert method == "chat.update"
    assert "Timed out — not run" in payload["text"]
