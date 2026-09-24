"""Unit tests for the event-loop liveness watchdog (Issue #3385).

Covers the pure, core-side primitive: policy validation, arm/disarm lifecycle,
that a healthy loop is never tripped, and that a wedged loop is detected. The
``dump_and_exit`` path (``os._exit``) is exercised via ``dump_only`` so tests
do not kill the interpreter.
"""

import asyncio
import os
import sys
import threading
import time

import pytest

from praisonaiagents.gateway import (
    LoopWatchdog,
    LoopWatchdogPolicy,
    StartupWatchdog,
)
from praisonaiagents.gateway.protocols import GATEWAY_RESTART_EXIT_CODE


def test_policy_defaults():
    p = LoopWatchdogPolicy()
    assert p.probe_interval_s == 5.0
    assert p.missed_probes_before_wedged == 3
    assert p.on_wedge == "dump_and_exit"
    assert p.exit_code == GATEWAY_RESTART_EXIT_CODE
    assert p.wedge_after_s == 15.0


def test_policy_validation():
    with pytest.raises(ValueError):
        LoopWatchdogPolicy(probe_interval_s=0)
    with pytest.raises(ValueError):
        LoopWatchdogPolicy(missed_probes_before_wedged=0)
    with pytest.raises(ValueError):
        LoopWatchdogPolicy(on_wedge="boom")


def test_policy_rejects_non_finite_interval():
    """NaN / inf probe intervals must be rejected (Event.wait/Thread.join)."""
    with pytest.raises(ValueError):
        LoopWatchdogPolicy(probe_interval_s=float("nan"))
    with pytest.raises(ValueError):
        LoopWatchdogPolicy(probe_interval_s=float("inf"))


def test_disarm_when_not_armed_is_safe():
    wd = LoopWatchdog()
    assert wd.armed is False
    wd.disarm()  # should not raise
    assert wd.armed is False


def _run_loop_for(loop, seconds):
    def _stop():
        loop.call_later(seconds, loop.stop)

    loop.call_soon(_stop)
    loop.run_forever()


def test_healthy_loop_not_tripped():
    """A responsive loop must never be declared wedged."""
    loop = asyncio.new_event_loop()
    policy = LoopWatchdogPolicy(
        probe_interval_s=0.02,
        missed_probes_before_wedged=3,
        on_wedge="dump_only",
    )
    wd = LoopWatchdog(policy)
    wd.arm(loop)
    assert wd.armed is True
    try:
        _run_loop_for(loop, 0.4)
    finally:
        wd.disarm()
        loop.close()
    assert wd.wedged is False
    assert wd.armed is False


def test_last_lag_ms_measured_on_healthy_loop():
    """A responsive loop reports a small, finite scheduling lag (Issue #4265)."""
    wd = LoopWatchdog()
    assert wd.last_lag_ms == 0.0  # nothing measured yet
    loop = asyncio.new_event_loop()
    policy = LoopWatchdogPolicy(
        probe_interval_s=0.02,
        missed_probes_before_wedged=3,
        on_wedge="dump_only",
    )
    wd = LoopWatchdog(policy)
    wd.arm(loop)
    try:
        _run_loop_for(loop, 0.3)
    finally:
        wd.disarm()
        loop.close()
    # A healthy loop ran the ack promptly: lag is measured and small.
    assert wd.last_lag_ms >= 0.0
    assert wd.last_lag_ms < 1000.0


def test_last_lag_ms_anchored_to_oldest_unacked_probe():
    """Multi-interval stalls are measured from the *oldest* unacked probe.

    Regression for Issue #4265: when the loop is stalled the watchdog keeps
    scheduling fresh acks that all queue behind the wedge. If each new probe
    overwrote the send-time anchor, the ack that finally runs would report only
    the gap since the newest probe, understating a severe stall. The anchor
    must stay pinned to the first still-unacked probe until an ack consumes it.
    """
    loop = asyncio.new_event_loop()
    wd = LoopWatchdog(
        LoopWatchdogPolicy(probe_interval_s=0.02, on_wedge="dump_only")
    )
    wd._loop = loop  # attach without arming the OS thread; drive probes by hand
    try:
        # Three probes scheduled while the loop is stalled (no ack runs between
        # them). The real _schedule_probe must keep the anchor pinned to the
        # first probe rather than advancing it on every call.
        wd._schedule_probe()
        first_anchor = wd._probe_sent_at
        assert first_anchor > 0.0
        time.sleep(0.02)
        wd._schedule_probe()
        time.sleep(0.02)
        wd._schedule_probe()
        assert wd._probe_sent_at == first_anchor  # never advanced past the oldest

        # The loop finally drains the burst of acks. The first _ack measures the
        # full stall from the oldest anchor and consumes it; later acks in the
        # burst see a zeroed anchor and leave the measured lag intact.
        loop.call_soon(wd._ack)
        loop.call_soon(wd._ack)
        loop.call_soon(wd._ack)
        loop.call_soon(loop.stop)
        loop.run_forever()
        # Elapsed since the oldest probe is ~0.04s+ (two 0.02s sleeps): the
        # reported lag reflects the full multi-interval stall, not ~0.
        assert wd.last_lag_ms >= 40.0
        assert wd._probe_sent_at == 0.0  # consumed → next probe re-anchors fresh
    finally:
        loop.close()


def test_wedged_loop_detected():
    """A loop blocked inside a sync call is detected (dump_only, no exit)."""
    loop = asyncio.new_event_loop()
    policy = LoopWatchdogPolicy(
        probe_interval_s=0.02,
        missed_probes_before_wedged=2,
        on_wedge="dump_only",
    )
    wd = LoopWatchdog(policy)

    def _wedge():
        # Block the loop thread synchronously to simulate a hang.
        time.sleep(0.5)

    wd.arm(loop)
    try:
        loop.call_soon(_wedge)
        _run_loop_for(loop, 0.7)
    finally:
        wd.disarm()
        loop.close()
    assert wd.wedged is True


def test_wedge_writes_dump_file(tmp_path):
    dump = tmp_path / "wedge.txt"
    loop = asyncio.new_event_loop()
    policy = LoopWatchdogPolicy(
        probe_interval_s=0.02,
        missed_probes_before_wedged=2,
        on_wedge="dump_only",
        dump_file=str(dump),
    )
    wd = LoopWatchdog(policy)

    def _wedge():
        time.sleep(0.5)

    wd.arm(loop)
    try:
        loop.call_soon(_wedge)
        _run_loop_for(loop, 0.7)
    finally:
        wd.disarm()
        loop.close()
    assert wd.wedged is True
    assert dump.exists()
    assert "wedged" in dump.read_text()


def test_arm_is_idempotent():
    loop = asyncio.new_event_loop()
    wd = LoopWatchdog(LoopWatchdogPolicy(probe_interval_s=0.05, on_wedge="dump_only"))
    wd.arm(loop)
    first = wd._thread
    wd.arm(loop)  # no-op
    assert wd._thread is first
    wd.disarm()
    loop.close()


def test_disarm_suppresses_in_flight_exit():
    """A disarm racing an in-flight wedge must not call os._exit."""
    wd = LoopWatchdog(
        LoopWatchdogPolicy(
            probe_interval_s=0.02,
            missed_probes_before_wedged=1,
            on_wedge="dump_and_exit",
        )
    )
    # Simulate disarm() having set the stop flag while the worker is mid-wedge.
    wd._stop.set()
    exited = []
    original_exit = os._exit
    os._exit = lambda code: exited.append(code)
    try:
        wd._on_wedge()  # must observe _stop and return without exiting
    finally:
        os._exit = original_exit
    assert exited == []
    assert wd.wedged is True


def test_closed_loop_does_not_trip():
    """Scheduling onto a closed loop is a normal shutdown, not a wedge."""
    loop = asyncio.new_event_loop()
    loop.close()
    policy = LoopWatchdogPolicy(
        probe_interval_s=0.02,
        missed_probes_before_wedged=2,
        on_wedge="dump_only",
    )
    wd = LoopWatchdog(policy)
    wd.arm(loop)
    time.sleep(0.2)
    wd.disarm()
    assert wd.wedged is False


# ── Shutdown-phase deadline mode (Issue #5079) ──


def test_policy_shutdown_grace_default_and_validation():
    assert LoopWatchdogPolicy().shutdown_grace_s == 5.0
    LoopWatchdogPolicy(shutdown_grace_s=0)  # zero is allowed
    with pytest.raises(ValueError):
        LoopWatchdogPolicy(shutdown_grace_s=-1)
    with pytest.raises(ValueError):
        LoopWatchdogPolicy(shutdown_grace_s=float("nan"))


def test_cancel_when_not_armed_is_safe():
    wd = LoopWatchdog()
    assert wd.deadline_armed is False
    wd.cancel()  # must not raise
    assert wd.deadline_armed is False
    assert wd.deadline_expired is False


def test_clean_shutdown_cancels_deadline_no_exit():
    """A deadline cancelled before expiry must never dump or self-exit."""
    wd = LoopWatchdog(
        LoopWatchdogPolicy(
            shutdown_grace_s=0.0, on_wedge="dump_and_exit"
        )
    )
    wd.arm_deadline(0.5)
    assert wd.deadline_armed is True
    wd.cancel()  # clean stop finished well before 0.5s
    assert wd.deadline_armed is False
    assert wd.deadline_expired is False


def test_wedged_shutdown_expires_deadline():
    """A shutdown that overruns the deadline records expiry (dump_only, no exit).

    Deterministic: drive the expiry handler directly with a fresh (unset)
    generation event rather than racing a real wall-clock sleep against a
    daemon thread.
    """
    wd = LoopWatchdog(
        LoopWatchdogPolicy(on_wedge="dump_only")
    )
    wd._on_deadline(0.05, threading.Event())
    assert wd.deadline_expired is True


def test_deadline_thread_actually_fires_and_expires():
    """End-to-end lifecycle: a short real deadline expires the daemon thread.

    Synchronised on the thread terminating (``join``) rather than a fixed
    sleep, so it stays deterministic under load.
    """
    wd = LoopWatchdog(LoopWatchdogPolicy(on_wedge="dump_only"))
    wd.arm_deadline(0.05)
    thread = wd._deadline_thread
    assert thread is not None
    thread.join(timeout=5.0)
    assert thread.is_alive() is False
    assert wd.deadline_expired is True


def test_deadline_arm_is_idempotent():
    wd = LoopWatchdog(LoopWatchdogPolicy(on_wedge="dump_only"))
    wd.arm_deadline(1.0)
    first = wd._deadline_thread
    wd.arm_deadline(1.0)  # no-op while armed
    assert wd._deadline_thread is first
    wd.cancel()


def test_deadline_writes_dump_file(tmp_path):
    """The expiry handler writes the dump file. Driven directly for determinism."""
    dump = tmp_path / "shutdown.txt"
    wd = LoopWatchdog(
        LoopWatchdogPolicy(on_wedge="dump_only", dump_file=str(dump))
    )
    wd._on_deadline(0.05, threading.Event())
    assert wd.deadline_expired is True
    assert dump.exists()
    assert "shutdown did not complete" in dump.read_text()


def test_deadline_cancel_suppresses_in_flight_exit():
    """A cancelled generation must neither self-exit nor record expiry."""
    wd = LoopWatchdog(
        LoopWatchdogPolicy(on_wedge="dump_and_exit")
    )
    stop = threading.Event()
    stop.set()  # simulate cancel() having raced in for this generation
    exited = []
    original_exit = os._exit
    os._exit = lambda code: exited.append(code)
    try:
        wd._on_deadline(1.0, stop)  # must observe its own stop flag and stay inert
    finally:
        os._exit = original_exit
    assert exited == []
    # A cancelled generation stays fully inert — it does not record expiry.
    assert wd.deadline_expired is False


def test_stale_generation_never_exits_after_rearm():
    """A stale, cancelled generation must not self-exit during a later run.

    Regression for the cancel/re-arm race: an old generation that survived the
    bounded join checks its *own* stop event, not the shared one a fresh arm
    would clear, so it can never ``os._exit`` a healthy later shutdown.
    """
    wd = LoopWatchdog(LoopWatchdogPolicy(on_wedge="dump_and_exit"))
    wd.arm_deadline(10.0)
    old_stop = wd._deadline_stop
    wd.cancel()  # old generation is cancelled: its event is set
    assert old_stop.is_set() is True

    # A fresh arm starts a brand-new generation with its own (unset) event.
    wd.arm_deadline(10.0)
    assert wd._deadline_stop is not old_stop
    assert wd._deadline_stop.is_set() is False

    exited = []
    original_exit = os._exit
    os._exit = lambda code: exited.append(code)
    try:
        # The stale generation fires its handler against its own (set) event.
        wd._on_deadline(10.0, old_stop)
    finally:
        os._exit = original_exit
    assert exited == []  # stale generation stayed inert
    wd.cancel()


def test_non_positive_deadline_is_noop():
    wd = LoopWatchdog()
    wd.arm_deadline(0)
    assert wd.deadline_armed is False
    wd.arm_deadline(-5)
    assert wd.deadline_armed is False


# ── Startup-phase watchdog (Issue #5265) ──


def test_startup_validation():
    with pytest.raises(ValueError):
        StartupWatchdog(on_expire="boom")
    with pytest.raises(ValueError):
        StartupWatchdog(max_extensions=-1)


def test_startup_defaults_and_initial_state():
    sw = StartupWatchdog()
    assert sw.on_expire == "dump_and_exit"
    assert sw.exit_code == GATEWAY_RESTART_EXIT_CODE
    assert sw.armed is False
    assert sw.expired is False
    assert sw.confirmed is False


def test_startup_non_positive_deadline_is_noop():
    sw = StartupWatchdog()
    sw.arm(deadline_s=0)
    assert sw.armed is False
    sw.arm(deadline_s=-1)
    assert sw.armed is False
    sw.arm(deadline_s=float("nan"))
    assert sw.armed is False


def test_startup_confirm_when_not_armed_is_safe():
    sw = StartupWatchdog()
    sw.confirm_loop_live()  # must not raise
    assert sw.confirmed is True
    assert sw.expired is False


def test_startup_progress_when_not_armed_is_safe():
    sw = StartupWatchdog()
    sw.report_startup_progress("noop")  # must not raise
    assert sw.armed is False


def test_startup_confirm_before_deadline_no_exit():
    """A startup that confirms the loop live before the deadline never exits."""
    sw = StartupWatchdog(on_expire="dump_and_exit")
    sw.arm(deadline_s=5.0)
    assert sw.armed is True
    sw.confirm_loop_live()  # loop came up promptly
    assert sw.armed is False
    assert sw.confirmed is True
    assert sw.expired is False


def test_startup_arm_is_idempotent():
    sw = StartupWatchdog(on_expire="dump_only")
    sw.arm(deadline_s=5.0)
    first = sw._thread
    sw.arm(deadline_s=5.0)  # no-op while armed
    assert sw._thread is first
    sw.confirm_loop_live()


def test_startup_deadline_expires_and_dumps(tmp_path):
    """A wedged startup expires, dumps stacks, records expiry (dump_only)."""
    dump = tmp_path / "startup.txt"
    sw = StartupWatchdog(on_expire="dump_only", dump_file=str(dump))
    sw.arm(deadline_s=0.05)
    thread = sw._thread
    assert thread is not None
    thread.join(timeout=5.0)
    assert thread.is_alive() is False
    assert sw.expired is True
    assert dump.exists()
    assert "startup did not confirm" in dump.read_text()


def test_startup_progress_extends_deadline():
    """Progress reports keep a slow-but-alive startup from being tripped."""
    sw = StartupWatchdog(on_expire="dump_only", max_extensions=10)
    sw.arm(deadline_s=0.1)
    # Nudge the deadline several times across a span longer than the base
    # deadline; a live startup reporting progress must not expire.
    for _ in range(4):
        time.sleep(0.05)
        sw.report_startup_progress("phase")
    assert sw.expired is False
    assert sw.armed is True
    sw.confirm_loop_live()
    assert sw.expired is False


def test_startup_extensions_are_bounded():
    """Once extensions are exhausted, a still-wedged phase trips the deadline."""
    sw = StartupWatchdog(on_expire="dump_only", max_extensions=2)
    sw.arm(deadline_s=0.05)
    sw.report_startup_progress("a")
    sw.report_startup_progress("b")
    # Third report is refused (bound reached); the phase then wedges.
    sw.report_startup_progress("c")
    thread = sw._thread
    assert thread is not None
    thread.join(timeout=5.0)
    assert sw.expired is True
    # Budget accounting is done by the watchdog thread (so batched reports never
    # lose the resets they paid for); it is exact once the thread has drained.
    assert sw._extensions_used == 2


def test_startup_batched_progress_does_not_waste_budget():
    """Reports batched before a wake each still buy a real deadline reset.

    Regression for the review finding "progress reports lose extensions": with
    per-call accounting, several reports landing between two wakes would each
    spend budget but only reset the window once, letting a later legitimate
    phase exhaust the budget early. With thread-side draining, a single slow
    boot that stays under the extension bound must survive well past its base
    deadline.
    """
    sw = StartupWatchdog(on_expire="dump_only", max_extensions=6)
    sw.arm(deadline_s=0.08)
    # Fire a burst of reports (likely batched) then keep reporting across a
    # span far longer than the base deadline; must not expire while affordable.
    sw.report_startup_progress("burst-1")
    sw.report_startup_progress("burst-2")
    for _ in range(4):
        time.sleep(0.05)
        sw.report_startup_progress("phase")
    assert sw.expired is False
    assert sw.armed is True
    sw.confirm_loop_live()
    assert sw.expired is False


def test_startup_confirm_suppresses_in_flight_exit():
    """A confirm racing an in-flight expiry must not call os._exit."""
    sw = StartupWatchdog(on_expire="dump_and_exit")
    stop = threading.Event()
    stop.set()  # simulate confirm_loop_live() having raced in
    exited = []
    original_exit = os._exit
    os._exit = lambda code: exited.append(code)
    try:
        sw._on_expire(stop)  # must observe its own stop flag and stay inert
    finally:
        os._exit = original_exit
    assert exited == []
    assert sw.expired is False


def test_startup_expiry_takes_active_exit_path():
    """The active exit path (stop NOT set) must dump and call os._exit.

    The in-flight-suppression test only exercises the first stop check; this one
    covers the real wedge path so a regression that silently stopped exiting
    would be caught (review: "exit race remains untested").
    """
    sw = StartupWatchdog(on_expire="dump_and_exit", exit_code=42)
    sw._dump_stacks_on_expire = True
    stop = threading.Event()  # deliberately NOT set: a genuine wedge
    dumped = []
    exited = []
    sw._dump_stacks = lambda: dumped.append(True)
    original_exit = os._exit
    os._exit = lambda code: exited.append(code)
    try:
        sw._on_expire(stop)
    finally:
        os._exit = original_exit
    assert dumped == [True]
    assert exited == [42]
    assert sw.expired is True


def test_startup_confirm_during_flush_suppresses_exit():
    """A confirm landing while the pre-exit flush blocks must cancel the exit.

    Simulates a full-pipe stderr.flush() that blocks long enough for
    confirm_loop_live() to set the stop event; the final re-check before
    os._exit must then honour it (review: "confirmation cannot prevent late
    exit").
    """
    sw = StartupWatchdog(on_expire="dump_and_exit")
    sw._dump_stacks_on_expire = False
    stop = threading.Event()  # NOT set initially: wedge path is taken

    exited = []
    original_exit = os._exit
    original_flush = sys.stderr.flush

    def blocking_flush():
        # The confirm races in "while" the flush is in progress.
        stop.set()

    os._exit = lambda code: exited.append(code)
    sys.stderr.flush = blocking_flush
    try:
        sw._on_expire(stop)
    finally:
        os._exit = original_exit
        sys.stderr.flush = original_flush
    assert exited == []  # final re-check honoured the racing confirm
    assert sw.expired is True


def test_startup_dump_stacks_can_be_disabled(tmp_path):
    dump = tmp_path / "nodump.txt"
    sw = StartupWatchdog(on_expire="dump_only", dump_file=str(dump))
    sw.arm(deadline_s=0.05, dump_stacks=False)
    thread = sw._thread
    assert thread is not None
    thread.join(timeout=5.0)
    assert sw.expired is True
    assert dump.exists() is False
