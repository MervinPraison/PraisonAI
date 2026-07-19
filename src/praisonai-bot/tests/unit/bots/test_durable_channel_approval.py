"""Tests for durable persistence across chat-channel approval backends.

Every chat backend (Slack, Telegram, Discord, Webhook, HTTP) now accepts an
optional ``store`` (:class:`ApprovalStore`). When supplied, the pending approval
is persisted before polling and the final decision recorded, so an outstanding
approval survives a process restart and can be rehydrated on startup. When no
store is given, behaviour is unchanged (legacy in-memory-only).
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from praisonai_bot.bots._approval_base import (
    DEFAULT_APPROVAL_TIMEOUT,
    DurableApprovalMixin,
)
from praisonai_bot.bots._approval_store import ApprovalStore


def _make_request(approval_id="dur-1", tool_name="deploy"):
    from praisonaiagents.approval import ApprovalRequest

    return ApprovalRequest(
        tool_name=tool_name,
        arguments={"target": "prod"},
        risk_level="high",
        approval_id=approval_id,
    )


def _store(tmp):
    return ApprovalStore(path=str(Path(tmp) / "approvals.sqlite"))


# ── Backends inherit the mixin & default timeout is shared ──────────────────

def test_all_chat_backends_are_durable():
    from praisonai_bot.bots._discord_approval import DiscordApproval
    from praisonai_bot.bots._http_approval import HTTPApproval
    from praisonai_bot.bots._slack_approval import SlackApproval
    from praisonai_bot.bots._telegram_approval import TelegramApproval
    from praisonai_bot.bots._webhook_approval import WebhookApproval

    for cls in (
        SlackApproval,
        TelegramApproval,
        DiscordApproval,
        WebhookApproval,
        HTTPApproval,
    ):
        assert issubclass(cls, DurableApprovalMixin)


def test_shared_default_timeout():
    assert DEFAULT_APPROVAL_TIMEOUT == 300.0


# ── Mixin persist / resolve / rehydrate semantics ───────────────────────────

def test_persist_makes_approval_survive_restart():
    async def run():
        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            request = _make_request("survive-1")

            backend = DurableApprovalMixin()
            backend._init_store(store)
            await backend._persist_pending(request, DEFAULT_APPROVAL_TIMEOUT)

            # Simulate restart: a brand-new backend pointed at the same store.
            fresh = DurableApprovalMixin()
            fresh._init_store(ApprovalStore(path=str(Path(tmp) / "approvals.sqlite")))
            pending = await fresh.rehydrate()
            assert len(pending) == 1
            approval_id, req = pending[0]
            assert approval_id == "survive-1"
            assert req.tool_name == "deploy"

    asyncio.run(run())


def test_resolve_closes_pending_row():
    async def run():
        from praisonaiagents.approval.protocols import ApprovalDecision

        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            request = _make_request("resolve-1")

            backend = DurableApprovalMixin()
            backend._init_store(store)
            await backend._persist_pending(request, DEFAULT_APPROVAL_TIMEOUT)
            assert store.pending_count() == 1

            await backend._resolve_pending(
                request, ApprovalDecision(approved=True, reason="ok")
            )
            # Resolved rows no longer show up as pending / rehydratable.
            assert store.pending_count() == 0
            assert await backend.rehydrate() == []

    asyncio.run(run())


def test_no_store_is_a_noop_and_backward_compatible():
    async def run():
        from praisonaiagents.approval.protocols import ApprovalDecision

        backend = DurableApprovalMixin()
        backend._init_store(None)
        request = _make_request("noop-1")

        # None of these should raise or persist anything.
        await backend._persist_pending(request, DEFAULT_APPROVAL_TIMEOUT)
        await backend._resolve_pending(
            request, ApprovalDecision(approved=False, reason="n/a")
        )
        assert await backend.rehydrate() == []

    asyncio.run(run())


# ── End-to-end through a concrete backend (HTTP, no network needed) ─────────

def test_http_backend_persists_then_resolves():
    async def run():
        from praisonai_bot.bots._http_approval import HTTPApproval

        with tempfile.TemporaryDirectory() as tmp:
            store = _store(tmp)
            backend = HTTPApproval(port=0, timeout=0.3, store=store)
            request = _make_request("http-1")

            # Stub the server + polling so no socket is opened.
            async def _no_server():
                return None

            backend._ensure_server = _no_server  # type: ignore[assignment]

            decision = await backend.request_approval(request)

            # Timed out (no decision) -> fails closed, and the durable row is
            # recorded (resolved), not left dangling as pending.
            assert decision.approved is False
            assert store.pending_count() == 0
            assert store.get("http-1") is not None

    asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
