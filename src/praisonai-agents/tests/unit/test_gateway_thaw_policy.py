"""Unit tests for gateway freeze-thaw (host-suspend gap) detection (Issue #4767).

Covers the pure, core-side decision of WallClockGapThawPolicy and
conformance with the ThawPolicy protocol.
"""

import pytest

from praisonaiagents.gateway import (
    ThawDecision,
    ThawPolicyProtocol,
    WallClockGapThawPolicy,
)


def test_protocol_conformance():
    policy = WallClockGapThawPolicy()
    assert isinstance(policy, ThawPolicyProtocol)


def test_invalid_intervals_raise():
    with pytest.raises(ValueError):
        WallClockGapThawPolicy(tick_interval_s=0)
    with pytest.raises(ValueError):
        WallClockGapThawPolicy(gap_threshold_s=-1)


def test_first_tick_only_seeds_baseline():
    policy = WallClockGapThawPolicy()
    decision = policy.observe(monotonic_now=100.0, wall_now=1_000.0)
    assert isinstance(decision, ThawDecision)
    assert decision.suspended is False
    assert decision.gap_seconds == 0.0


def test_normal_tick_reports_no_gap():
    policy = WallClockGapThawPolicy(tick_interval_s=15.0, gap_threshold_s=60.0)
    policy.observe(monotonic_now=100.0, wall_now=1_000.0)
    # Both clocks advance together by ~one tick interval.
    decision = policy.observe(monotonic_now=115.0, wall_now=1_015.0)
    assert decision.suspended is False


def test_host_suspend_detected():
    policy = WallClockGapThawPolicy(tick_interval_s=15.0, gap_threshold_s=60.0)
    policy.observe(monotonic_now=100.0, wall_now=1_000.0)
    # Host frozen 40 min: wall-clock jumps 2400s, monotonic barely moves.
    decision = policy.observe(monotonic_now=100.5, wall_now=3_400.0)
    assert decision.suspended is True
    assert decision.gap_seconds == pytest.approx(2_399.5)
    assert decision.restart_transports is True
    assert decision.reconcile_schedule is True


def test_small_jitter_below_threshold_ignored():
    policy = WallClockGapThawPolicy(tick_interval_s=15.0, gap_threshold_s=60.0)
    policy.observe(monotonic_now=100.0, wall_now=1_000.0)
    # A late tick (loop stall) where both clocks moved together is not a
    # suspend: wall barely leads monotonic.
    decision = policy.observe(monotonic_now=150.0, wall_now=1_050.0)
    assert decision.suspended is False


def test_forward_wall_clock_correction_not_suspend():
    # NTP step / manual clock set jumps wall forward while the process is
    # running normally: monotonic keeps advancing on schedule. This must NOT
    # be classified as a host suspend (Greptile P1) — disrupting healthy
    # transports and reconciling the scheduler against a nonexistent freeze.
    policy = WallClockGapThawPolicy(tick_interval_s=15.0, gap_threshold_s=60.0)
    policy.observe(monotonic_now=100.0, wall_now=1_000.0)
    # Monotonic advanced a full tick (process alive, loop kept running);
    # wall jumped 200s forward from an NTP step.
    decision = policy.observe(monotonic_now=116.0, wall_now=1_216.0)
    assert decision.suspended is False
    assert decision.restart_transports is False
    assert decision.reconcile_schedule is False


def test_disabled_policy_never_reports():
    policy = WallClockGapThawPolicy(enabled=False)
    policy.observe(monotonic_now=100.0, wall_now=1_000.0)
    decision = policy.observe(monotonic_now=100.5, wall_now=3_400.0)
    assert decision.suspended is False


def test_thaw_decision_is_frozen():
    decision = ThawDecision(suspended=True, gap_seconds=10.0)
    with pytest.raises(Exception):
        decision.gap_seconds = 20.0  # type: ignore[misc]
