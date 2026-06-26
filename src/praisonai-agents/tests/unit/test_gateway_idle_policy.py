"""Unit tests for gateway idle-dormancy / scale-to-zero (Issue #2332).

Covers the pure, core-side decision predicates of ScaleToZeroPolicy and
conformance with the GatewayIdlePolicy protocol.
"""

import pytest

from praisonaiagents.gateway import (
    GatewayIdlePolicy,
    IdleDecision,
    ScaleToZeroPolicy,
)


def test_protocol_conformance():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5)
    assert isinstance(policy, GatewayIdlePolicy)


def test_invalid_timeout_raises():
    with pytest.raises(ValueError):
        ScaleToZeroPolicy(idle_timeout_minutes=0)
    with pytest.raises(ValueError):
        ScaleToZeroPolicy(idle_timeout_minutes=-1)


def test_idle_timeout_seconds():
    assert ScaleToZeroPolicy(idle_timeout_minutes=5).idle_timeout_seconds == 300.0


def test_idle_when_quiescent_past_timeout():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5)
    decision = policy.is_idle(
        running_turns=0,
        last_inbound_ts=0.0,
        has_background_work=False,
        now=301.0,
    )
    assert isinstance(decision, IdleDecision)
    assert decision.idle is True


def test_not_idle_before_timeout():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5)
    decision = policy.is_idle(
        running_turns=0,
        last_inbound_ts=0.0,
        has_background_work=False,
        now=120.0,
    )
    assert decision.idle is False
    assert "to idle" in decision.reason


def test_in_flight_turn_blocks_dormancy():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5)
    decision = policy.is_idle(
        running_turns=1,
        last_inbound_ts=0.0,
        has_background_work=False,
        now=10_000.0,
    )
    assert decision.idle is False
    assert "in flight" in decision.reason


def test_background_work_blocks_dormancy():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5)
    decision = policy.is_idle(
        running_turns=0,
        last_inbound_ts=0.0,
        has_background_work=True,
        now=10_000.0,
    )
    assert decision.idle is False
    assert "background" in decision.reason


def test_disabled_policy_never_idle():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5, enabled=False)
    decision = policy.is_idle(
        running_turns=0,
        last_inbound_ts=0.0,
        has_background_work=False,
        now=10_000.0,
    )
    assert decision.idle is False


def test_should_arm_requires_wake_and_quiescable():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5, wake_url="https://x/_wake")
    assert policy.should_arm(transports_quiescable=True, wake_registered=True) is True
    assert policy.should_arm(transports_quiescable=False, wake_registered=True) is False
    assert policy.should_arm(transports_quiescable=True, wake_registered=False) is False


def test_disabled_policy_never_arms():
    policy = ScaleToZeroPolicy(idle_timeout_minutes=5, enabled=False)
    assert policy.should_arm(transports_quiescable=True, wake_registered=True) is False
