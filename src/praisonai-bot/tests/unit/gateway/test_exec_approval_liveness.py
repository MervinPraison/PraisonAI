"""Tests for turn-liveness binding of gateway approvals (issue #4598).

Verifies that a pending approval bound to a session/run-generation is:
  - cancelled (fail-closed) when its turn is superseded/stopped, unblocking the
    awaiting caller promptly (so ``/stop`` produces a visible outcome); and
  - dropped at the resolution boundary if a resolution arrives after the turn
    was superseded (no stale tool execution / reply); while
  - unbound requests (no session/generation) keep today's behaviour.
"""

import asyncio

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
        _rid, _future = await mgr.register(
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
        # late resolution hitting a stale turn. With fail-closed registration
        # this future is denied at register() time; either way the reviewer's
        # late approval must be dropped and the future resolves "superseded".
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


def test_register_after_supersede_is_denied_immediately(tmp_path):
    """Registering for an already-superseded generation fail-closes at once.

    Guards the TOCTOU window: if /stop marks the generation before the tool's
    register() call lands, the caller must not park on a future no cancel batch
    will ever complete.
    """
    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")

    async def go():
        mgr.cancel_for_generation("s1", 5)  # supersede up to gen 5
        rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "rm -rf x"},
            agent_name="a",
            session_id="s1",
            run_generation=5,  # <= superseded -> denied at registration
        )
        # Not inserted: a resolve finds nothing.
        assert mgr.resolve(rid, Resolution(approved=True)) is False
        assert future.done()
        return await future

    res = asyncio.run(go())
    assert res.approved is False
    assert res.reason == "superseded"


def test_non_integer_run_generation_registers_unbound(tmp_path):
    """A non-integer run_generation must not break cancellation.

    An un-coercible generation drops the (untrustworthy) binding to unbound so
    the request still resolves normally instead of silently un-cancellable.
    """
    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")

    async def go():
        rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "ls"},
            agent_name="a",
            session_id="s1",
            run_generation="not-an-int",  # type: ignore[arg-type]
        )
        # Unbound -> a matching cancel does not touch it and resolve works.
        assert mgr.cancel_for_generation("s1", 1) == 0
        assert mgr.resolve(rid, Resolution(approved=True)) is True
        return await future

    res = asyncio.run(go())
    assert res.approved is True


def test_supersede_callback_wires_stop_to_cancel(tmp_path):
    """End-to-end: SessionRunControl.stop() cancels the turn's pending approval.

    Exercises the production wiring (``make_approval_supersede_callback`` +
    ``on_supersede``) rather than calling the manager in isolation, so /stop
    genuinely unblocks an approval-parked turn.
    """
    from praisonai_bot.bots._run_control import (
        SessionRunControl,
        make_approval_supersede_callback,
    )

    mgr = ExecApprovalManager(ttl=300, allowlist_path=tmp_path / "allow.sqlite")
    run_control = SessionRunControl(
        busy_mode="interrupt",
        on_supersede=make_approval_supersede_callback(mgr),
    )

    async def go():
        # Start a run so the session has generation 1, then park an approval
        # bound to (user, gen) exactly as the gateway would.
        assert (await run_control.submit("user1", "deploy")).value == "run_now"
        gen = run_control.get_run_status("user1")["run_generation"]
        _rid, future = await mgr.register(
            tool_name="shell_exec",
            arguments={"cmd": "deploy"},
            agent_name="a",
            session_id="user1",
            run_generation=gen,
        )
        # /stop must fire on_supersede -> cancel_for_generation -> unblock.
        assert await run_control.stop("user1") is True
        return await future

    res = asyncio.run(go())
    assert res.approved is False
    assert res.reason == "cancelled"
