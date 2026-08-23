"""Unit tests for the event-loop liveness watchdog (Issue #3385).

Covers the pure, core-side primitive: policy validation, arm/disarm lifecycle,
that a healthy loop is never tripped, and that a wedged loop is detected. The
``dump_and_exit`` path (``os._exit``) is exercised via ``dump_only`` so tests
do not kill the interpreter.
"""

import asyncio
import os
import threading
import time

import pytest

from praisonaiagents.gateway import LoopWatchdog, LoopWatchdogPolicy
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
