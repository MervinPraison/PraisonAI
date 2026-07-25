"""Unit tests for the event-loop liveness watchdog (Issue #3385).

Covers the pure, core-side primitive: policy validation, arm/disarm lifecycle,
that a healthy loop is never tripped, and that a wedged loop is detected. The
``dump_and_exit`` path (``os._exit``) is exercised via ``dump_only`` so tests
do not kill the interpreter.
"""

import asyncio
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
