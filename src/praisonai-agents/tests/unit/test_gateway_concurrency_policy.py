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
    MemoryPressurePolicy,
    ResourcePressurePolicyProtocol,
    ResourceSample,
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


# ---------------------------------------------------------------------------
# Per-tenant / per-scope concurrency fairness (Issue #5168)
# ---------------------------------------------------------------------------


def test_per_scope_disabled_by_default_matches_global():
    # No per-scope sub-limit: scope args are ignored, global-only behaviour.
    policy = ConcurrencyLimitPolicy(max_concurrent_runs=8, queue_depth=32)
    assert policy.max_concurrent_runs_per_scope == 0
    # A tenant with many in-flight but global slot free -> ADMIT (unchanged).
    assert (
        policy.decide(
            in_flight=0, queued=0, scope="tenant:acme", scope_in_flight=99
        )
        is AdmissionDecision.ADMIT
    )


def test_per_scope_queues_when_scope_at_sublimit_global_free():
    # Global slot notionally free (in_flight < ceiling) but the scope is at its
    # own sub-limit -> QUEUE against its slice, protecting quiet tenants.
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=8,
        queue_depth=32,
        max_concurrent_runs_per_scope=3,
    )
    assert (
        policy.decide(
            in_flight=3,
            queued=0,
            scope="tenant:acme",
            scope_in_flight=3,
            scope_queued=0,
        )
        is AdmissionDecision.QUEUE
    )


def test_per_scope_admits_below_sublimit():
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=8,
        queue_depth=32,
        max_concurrent_runs_per_scope=3,
    )
    assert (
        policy.decide(
            in_flight=5, queued=0, scope="tenant:acme", scope_in_flight=2
        )
        is AdmissionDecision.ADMIT
    )


def test_per_scope_rejects_when_scope_queue_full():
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=8,
        queue_depth=1,
        max_concurrent_runs_per_scope=3,
        overflow_policy="reject",
    )
    assert (
        policy.decide(
            in_flight=3,
            queued=0,
            scope="tenant:acme",
            scope_in_flight=3,
            scope_queued=1,
        )
        is AdmissionDecision.REJECT
    )


def test_per_scope_ignored_when_scope_empty():
    # Sub-limit configured but caller is unscoped -> fall through to global.
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=8,
        queue_depth=32,
        max_concurrent_runs_per_scope=3,
    )
    assert (
        policy.decide(in_flight=0, queued=0, scope="", scope_in_flight=99)
        is AdmissionDecision.ADMIT
    )


def test_global_ceiling_still_applies_under_sublimit():
    # A tenant below its sub-limit still queues once the global ceiling is hit.
    policy = ConcurrencyLimitPolicy(
        max_concurrent_runs=2,
        queue_depth=4,
        max_concurrent_runs_per_scope=5,
    )
    assert (
        policy.decide(
            in_flight=2, queued=0, scope="tenant:acme", scope_in_flight=1
        )
        is AdmissionDecision.QUEUE
    )


@pytest.mark.parametrize("bad", [-1, "x"])
def test_invalid_max_concurrent_runs_per_scope_raises(bad):
    with pytest.raises(ValueError):
        ConcurrencyLimitPolicy(
            max_concurrent_runs=8, max_concurrent_runs_per_scope=bad
        )


def test_gateway_config_per_scope_default_and_roundtrip():
    cfg = GatewayConfig()
    assert cfg.max_concurrent_runs_per_scope == 0
    cfg2 = GatewayConfig(
        max_concurrent_runs=8, max_concurrent_runs_per_scope=3
    )
    assert cfg2.to_dict()["max_concurrent_runs_per_scope"] == 3
    with pytest.raises(ValueError):
        GatewayConfig(max_concurrent_runs_per_scope=-1)


# ---------------------------------------------------------------------------
# Resource-pressure admission (Issue #3445)
# ---------------------------------------------------------------------------


def test_resource_policy_protocol_conformance():
    policy = MemoryPressurePolicy(soft_rss_mb=400, hard_rss_mb=550)
    assert isinstance(policy, ResourcePressurePolicyProtocol)


def test_resource_policy_disabled_admits_everything():
    policy = MemoryPressurePolicy()  # no thresholds
    assert policy.enabled is False
    assert policy.evaluate(ResourceSample(rss_mb=99999)) is AdmissionDecision.ADMIT


def test_resource_policy_admits_below_soft():
    policy = MemoryPressurePolicy(soft_rss_mb=400, hard_rss_mb=550)
    assert policy.evaluate(ResourceSample(rss_mb=399.9)) is AdmissionDecision.ADMIT


def test_resource_policy_queues_at_soft():
    policy = MemoryPressurePolicy(soft_rss_mb=400, hard_rss_mb=550)
    assert policy.evaluate(ResourceSample(rss_mb=400)) is AdmissionDecision.QUEUE
    assert policy.evaluate(ResourceSample(rss_mb=549)) is AdmissionDecision.QUEUE


def test_resource_policy_rejects_at_hard():
    policy = MemoryPressurePolicy(soft_rss_mb=400, hard_rss_mb=550)
    assert policy.evaluate(ResourceSample(rss_mb=550)) is AdmissionDecision.REJECT
    assert policy.evaluate(ResourceSample(rss_mb=9999)) is AdmissionDecision.REJECT


def test_resource_policy_missing_sample_admits():
    policy = MemoryPressurePolicy(soft_rss_mb=400, hard_rss_mb=550)
    assert policy.evaluate(ResourceSample(rss_mb=None)) is AdmissionDecision.ADMIT
    assert policy.evaluate(ResourceSample()) is AdmissionDecision.ADMIT


def test_resource_policy_hard_only():
    policy = MemoryPressurePolicy(hard_rss_mb=550)
    assert policy.enabled is True
    assert policy.evaluate(ResourceSample(rss_mb=100)) is AdmissionDecision.ADMIT
    assert policy.evaluate(ResourceSample(rss_mb=550)) is AdmissionDecision.REJECT


@pytest.mark.parametrize("bad", [-1, "x"])
def test_resource_policy_invalid_soft_raises(bad):
    with pytest.raises(ValueError):
        MemoryPressurePolicy(soft_rss_mb=bad)


def test_resource_policy_soft_above_hard_raises():
    with pytest.raises(ValueError):
        MemoryPressurePolicy(soft_rss_mb=600, hard_rss_mb=400)
