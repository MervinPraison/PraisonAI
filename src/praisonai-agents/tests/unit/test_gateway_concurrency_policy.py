"""Unit tests for gateway inbound admission control (Issue #2454).

Covers the pure, core-side decision predicate of ConcurrencyLimitPolicy and
conformance with the GatewayConcurrencyPolicy protocol, plus the GatewayConfig
schema fields for the 3-way (CLI/YAML/Python) surface.
"""

import pytest

from praisonaiagents.gateway import (
    AdmissionDecision,
    ConcurrencyLimitPolicy,
    GatewayConcurrencyPolicyProtocol,
    GatewayConfig,
)


def test_protocol_conformance():
    policy = ConcurrencyLimitPolicy(max_concurrent_runs=32, queue_depth=128)
    assert isinstance(policy, GatewayConcurrencyPolicyProtocol)


def test_disabled_admits_everything():
    policy = ConcurrencyLimitPolicy()  # max_concurrent_runs == 0
    assert policy.enabled is False
    assert policy.decide(in_flight=999, queued=999) is AdmissionDecision.ADMIT


def test_admits_below_ceiling():
    policy = ConcurrencyLimitPolicy(max_concurrent_runs=2, queue_depth=1)
    assert policy.decide(in_flight=0, queued=0) is AdmissionDecision.ADMIT
    assert policy.decide(in_flight=1, queued=0) is AdmissionDecision.ADMIT


def test_queues_at_ceiling_with_room():
    policy = ConcurrencyLimitPolicy(max_concurrent_runs=2, queue_depth=2)
    assert policy.decide(in_flight=2, queued=0) is AdmissionDecision.QUEUE
    assert policy.decide(in_flight=2, queued=1) is AdmissionDecision.QUEUE


def test_rejects_when_queue_full_reject_policy():
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=2, queue_depth=1, overflow_policy="reject"
    )
    assert policy.decide(in_flight=2, queued=1) is AdmissionDecision.REJECT


def test_queue_overflow_keeps_queueing():
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=2, queue_depth=1, overflow_policy="queue"
    )
    assert policy.decide(in_flight=2, queued=99) is AdmissionDecision.QUEUE


def test_shed_oldest_keeps_queueing():
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=2, queue_depth=1, overflow_policy="shed_oldest"
    )
    assert policy.decide(in_flight=2, queued=1) is AdmissionDecision.QUEUE


@pytest.mark.parametrize("bad", [-1, "x"])
def test_invalid_max_concurrent_runs_raises(bad):
    with pytest.raises(ValueError):
        ConcurrencyLimitPolicy(max_concurrent_runs=bad)


def test_invalid_overflow_policy_raises():
    with pytest.raises(ValueError):
        ConcurrencyLimitPolicy(max_concurrent_runs=1, overflow_policy="explode")


def test_gateway_config_defaults_disable_admission():
    cfg = GatewayConfig()
    assert cfg.max_concurrent_runs == 0
    assert cfg.queue_depth == 0
    assert cfg.overflow_policy == "reject"


def test_gateway_config_roundtrip():
    cfg = GatewayConfig(
        max_concurrent_runs=32, queue_depth=128, overflow_policy="queue"
    )
    d = cfg.to_dict()
    assert d["max_concurrent_runs"] == 32
    assert d["queue_depth"] == 128
    assert d["overflow_policy"] == "queue"


def test_gateway_config_validation():
    with pytest.raises(ValueError):
        GatewayConfig(max_concurrent_runs=-1)
    with pytest.raises(ValueError):
        GatewayConfig(overflow_policy="nope")
