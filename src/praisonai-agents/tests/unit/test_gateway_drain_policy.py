"""Unit tests for gateway graceful-drain on shutdown (Issue #2375).

Covers the pure, core-side decision predicate of DrainTimeoutPolicy and
conformance with the GatewayDrainPolicy protocol.
"""

import pytest

from praisonaiagents.gateway import (
    DrainDecision,
    DrainTimeoutPolicy,
    GatewayDrainPolicyProtocol,
)


def test_protocol_conformance():
    policy = DrainTimeoutPolicy(drain_timeout_seconds=30)
    assert isinstance(policy, GatewayDrainPolicyProtocol)


def test_invalid_timeout_raises():
    with pytest.raises(ValueError):
        DrainTimeoutPolicy(drain_timeout_seconds=-1)


def test_zero_timeout_disables_drain():
    policy = DrainTimeoutPolicy(drain_timeout_seconds=0)
    decision = policy.should_keep_draining(running_turns=3, seconds_elapsed=0.0)
    assert isinstance(decision, DrainDecision)
    assert decision.keep_draining is False
    assert "disabled" in decision.reason


def test_keeps_draining_with_turns_in_flight():
    policy = DrainTimeoutPolicy(drain_timeout_seconds=30)
    decision = policy.should_keep_draining(running_turns=2, seconds_elapsed=5.0)
    assert decision.keep_draining is True
    assert "in flight" in decision.reason


def test_stops_draining_when_no_turns():
    policy = DrainTimeoutPolicy(drain_timeout_seconds=30)
    decision = policy.should_keep_draining(running_turns=0, seconds_elapsed=5.0)
    assert decision.keep_draining is False
    assert "no agent turns" in decision.reason


def test_stops_draining_at_timeout_with_abandoned_turns():
    policy = DrainTimeoutPolicy(drain_timeout_seconds=30)
    decision = policy.should_keep_draining(running_turns=1, seconds_elapsed=30.0)
    assert decision.keep_draining is False
    assert "drain timeout" in decision.reason


def test_stops_draining_past_timeout():
    policy = DrainTimeoutPolicy(drain_timeout_seconds=30)
    decision = policy.should_keep_draining(running_turns=4, seconds_elapsed=45.0)
    assert decision.keep_draining is False


def test_timeout_seconds_stored_as_float():
    policy = DrainTimeoutPolicy(drain_timeout_seconds=15)
    assert policy.drain_timeout_seconds == 15.0
    assert isinstance(policy.drain_timeout_seconds, float)
