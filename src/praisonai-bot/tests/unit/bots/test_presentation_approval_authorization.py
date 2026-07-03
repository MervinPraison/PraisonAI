"""Tests for actor-authorization, audit, and replay protection in the
presentation-based tool approval handler."""

import asyncio

import pytest

from praisonai_bot.bots._presentation_approval import PresentationApprovalHandler


async def _resolve_later(handler, approval_id, decision, actor, delay=0.01):
    await asyncio.sleep(delay)
    return await handler.handle_approval_command(approval_id, decision, actor=actor)


def test_unauthorized_actor_cannot_resolve():
    async def run():
        handler = PresentationApprovalHandler()

        async def request():
            return await handler.request_approval(
                tool_name="delete_file",
                arguments={"path": "/etc/passwd"},
                allowed_actors={"requester", "admin"},
                timeout=0.2,
            )

        async def attacker():
            await asyncio.sleep(0.01)
            # Grab the only pending approval id
            approval_id = next(iter(handler._pending_approvals))
            return await handler.handle_approval_command(
                approval_id, "allow", actor="999"
            )

        result, attacker_handled = await asyncio.gather(request(), attacker())
        return result, attacker_handled

    result, attacker_handled = asyncio.run(run())
    # Attacker's click is rejected and the request times out (fail-closed)
    assert attacker_handled is False
    assert result["approved"] is False
    assert "timed out" in result["reason"]


def test_authorized_actor_resolves():
    async def run():
        handler = PresentationApprovalHandler()

        async def request():
            return await handler.request_approval(
                tool_name="delete_file",
                arguments={"path": "sample/path.txt"},
                allowed_actors={"requester", "admin"},
                timeout=1.0,
            )

        async def approver():
            await asyncio.sleep(0.01)
            approval_id = next(iter(handler._pending_approvals))
            return await handler.handle_approval_command(
                approval_id, "allow", actor="admin"
            ), approval_id

        result, (handled, approval_id) = await asyncio.gather(request(), approver())
        return result, handled, approval_id, handler.audit_log

    result, handled, approval_id, audit = asyncio.run(run())
    assert handled is True
    assert result["approved"] is True
    # Audit records who/what/decision
    entry = next(e for e in audit if e["approval_id"] == approval_id)
    assert entry["actor"] == "admin"
    assert entry["decision"] == "allow"
    assert entry["approved"] is True
    assert entry["authorized"] is True


def test_replay_is_noop():
    async def run():
        handler = PresentationApprovalHandler()

        async def request():
            return await handler.request_approval(
                tool_name="t",
                arguments={},
                allowed_actors={"admin"},
                timeout=1.0,
            )

        async def approver():
            await asyncio.sleep(0.01)
            approval_id = next(iter(handler._pending_approvals))
            first = await handler.handle_approval_command(
                approval_id, "allow", actor="admin"
            )
            # Duplicate / late callback for the same id
            second = await handler.handle_approval_command(
                approval_id, "allow", actor="admin"
            )
            return first, second

        _result, (first, second) = await asyncio.gather(request(), approver())
        return first, second

    first, second = asyncio.run(run())
    assert first is True
    assert second is False  # replay rejected


def test_no_allowed_actors_is_backward_compatible():
    async def run():
        handler = PresentationApprovalHandler()

        async def request():
            return await handler.request_approval(
                tool_name="t", arguments={}, timeout=1.0
            )

        async def approver():
            await asyncio.sleep(0.01)
            approval_id = next(iter(handler._pending_approvals))
            # Any actor (even None) can resolve when no restriction set
            return await handler.handle_approval_command(
                approval_id, "allow", actor="anyone"
            )

        result, handled = await asyncio.gather(request(), approver())
        return result, handled

    result, handled = asyncio.run(run())
    assert handled is True
    assert result["approved"] is True


def test_is_authorized_helper():
    async def run():
        handler = PresentationApprovalHandler()
        fut_task = asyncio.ensure_future(
            handler.request_approval(
                tool_name="t",
                arguments={},
                allowed_actors={"admin"},
                timeout=0.1,
            )
        )
        await asyncio.sleep(0.01)
        approval_id = next(iter(handler._pending_approvals))
        authorized = handler.is_authorized(approval_id, "admin")
        unauthorized = handler.is_authorized(approval_id, "999")
        unknown = handler.is_authorized("deadbeef", "admin")
        await fut_task
        return authorized, unauthorized, unknown

    authorized, unauthorized, unknown = asyncio.run(run())
    assert authorized is True
    assert unauthorized is False
    assert unknown is False


def test_replay_and_audit_state_is_bounded():
    async def run():
        handler = PresentationApprovalHandler(history_limit=3)
        for _ in range(5):
            fut = asyncio.ensure_future(
                handler.request_approval(tool_name="t", arguments={}, timeout=1.0)
            )
            await asyncio.sleep(0)
            approval_id = next(iter(handler._pending_approvals))
            await handler.handle_approval_command(approval_id, "allow")
            await fut
        return handler

    handler = asyncio.run(run())
    # Both replay and audit state are capped at history_limit.
    assert len(handler._resolved_ids) == 3
    assert len(handler._resolved_order) == 3
    assert len(handler.audit_log) == 3


def test_audit_log_returns_copies():
    async def run():
        handler = PresentationApprovalHandler()
        fut = asyncio.ensure_future(
            handler.request_approval(tool_name="t", arguments={}, timeout=1.0)
        )
        await asyncio.sleep(0)
        approval_id = next(iter(handler._pending_approvals))
        await handler.handle_approval_command(approval_id, "allow", actor="admin")
        await fut
        return handler

    handler = asyncio.run(run())
    snapshot = handler.audit_log
    snapshot[0]["actor"] = "tampered"
    # Mutating the returned copy must not affect internal state.
    assert handler.audit_log[0]["actor"] == "admin"
