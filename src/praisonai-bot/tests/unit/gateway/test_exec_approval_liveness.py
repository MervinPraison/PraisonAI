"""Tests for turn-liveness binding of gateway approvals (issue #4598).

Verifies that a pending approval bound to a session/run-generation is:
  - cancelled (fail-closed) when its turn is superseded/stopped, unblocking the
    awaiting caller promptly (so ``/stop`` produces a visible outcome); and
  - dropped at the resolution boundary if a resolution arrives after the turn
    was superseded (no stale tool execution / reply); while
  - unbound requests (no session/generation) keep today's behaviour.
"""

import asyncio

import pytest

from praisonai_bot.gateway.exec_approval import (
    ExecApprovalManager,
    Resolution,
)


def test_unbound_request_is_always_live(tmp_path):
    """A request with no session/generation resolves normally (unchanged)."""
    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")

    async def go():
        rid, future = await mgr.register(
            tool_name="shell_exec", arguments={"cmd": "ls"}, agent_name="a"
        )
        assert mgr.resolve(rid, Resolution(approved=True)) is True
        return await future

    res = asyncio.run(go())
    assert res.approved is True


def test_cancel_for_generation_unblocks_pending(tmp_path):
    """A /stop-style cancel completes the pending future as denied promptly."""
    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")

    async def go():
        rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "rm -rf x"},
            agent_name="a",
            session_id="s1",
            run_generation=1,
        )
        n = mgr.cancel_for_generation("s1", 1)
        assert n == 1
        return rid, await future

    rid, res = asyncio.run(go())
    assert res.approved is False
    assert res.reason == "cancelled"
    # The request is gone; a later resolve is a no-op.
    assert mgr.resolve(rid, Resolution(approved=True)) is False


def test_stale_resolution_is_dropped(tmp_path):
    """A resolution arriving after supersede is dropped (fail-closed)."""
    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")

    async def go():
        rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "deploy"},
            agent_name="a",
            session_id="s1",
            run_generation=1,
        )
        # Turn superseded by a newer generation, but this old pending was not
        # in the cancel batch (e.g. registered independently); mark superseded.
        mgr.cancel_for_generation("s1", 1)
        # Re-register a fresh pending for the SAME old generation to simulate a
        # late resolution hitting a stale turn.
        rid2, future2 = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "deploy"},
            agent_name="a",
            session_id="s1",
            run_generation=1,
        )
        # Reviewer approves the stale turn -> must be dropped.
        assert mgr.resolve(rid2, Resolution(approved=True)) is False
        return await future2

    res = asyncio.run(go())
    assert res.approved is False
    assert res.reason == "superseded"


def test_newer_generation_still_live(tmp_path):
    """Superseding an old generation does not affect a newer one."""
    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")

    async def go():
        mgr.cancel_for_generation("s1", 1)  # supersede gen 1
        rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "ls"},
            agent_name="a",
            session_id="s1",
            run_generation=2,  # newer, still live
        )
        assert mgr.resolve(rid, Resolution(approved=True)) is True
        return await future

    res = asyncio.run(go())
    assert res.approved is True
