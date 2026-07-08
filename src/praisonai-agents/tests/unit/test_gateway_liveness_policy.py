"""Unit tests for application-level connection liveness (Issue #2798).

Covers the pure, core-side decision predicate of LivenessPolicy, its
protocol conformance, the PING/PONG event types, the LIVENESS_TIMEOUT close
code, and the LivenessConfig -> LivenessPolicy bridge.
"""

import pytest

from praisonaiagents.gateway import (
    EventType,
    GatewayCloseCode,
    LivenessConfig,
    LivenessDecision,
    LivenessPolicy,
    LivenessPolicyProtocol,
)


def test_protocol_conformance():
    policy = LivenessPolicy(interval_ms=30_000, missed_beats_before_reap=2)
    assert isinstance(policy, LivenessPolicyProtocol)


def test_ping_pong_event_types_exist():
    assert EventType.PING.value == "ping"
    assert EventType.PONG.value == "pong"


def test_liveness_timeout_close_code_exists():
    assert GatewayCloseCode.LIVENESS_TIMEOUT.value == "liveness_timeout"


def test_defaults():
    policy = LivenessPolicy()
    assert policy.interval_ms == 30_000
    assert policy.missed_beats_before_reap == 2
    assert policy.enabled is True
    assert policy.interval_seconds == 30.0


def test_invalid_interval_raises():
    with pytest.raises(ValueError):
        LivenessPolicy(interval_ms=-1)


def test_invalid_missed_beats_raises():
    with pytest.raises(ValueError):
        LivenessPolicy(missed_beats_before_reap=0)


def test_keeps_fresh_connection():
    policy = LivenessPolicy(interval_ms=30_000, missed_beats_before_reap=2)
    # now is only 10s past last activity; deadline is 60s.
    decision = policy.evaluate(last_activity=1000.0, now=1010.0)
    assert isinstance(decision, LivenessDecision)
    assert decision is LivenessDecision.KEEP


def test_reaps_stale_connection():
    policy = LivenessPolicy(interval_ms=30_000, missed_beats_before_reap=2)
    # deadline = 1000 + 30 * 2 = 1060; now is past it.
    decision = policy.evaluate(last_activity=1000.0, now=1061.0)
    assert decision is LivenessDecision.REAP


def test_boundary_at_deadline_keeps():
    policy = LivenessPolicy(interval_ms=30_000, missed_beats_before_reap=2)
    # Exactly at the deadline is not "> deadline", so KEEP.
    decision = policy.evaluate(last_activity=1000.0, now=1060.0)
    assert decision is LivenessDecision.KEEP


def test_reap_deadline_arithmetic():
    policy = LivenessPolicy(interval_ms=10_000, missed_beats_before_reap=3)
    assert policy.reap_deadline(100.0) == pytest.approx(100.0 + 10.0 * 3)


def test_zero_interval_disables_reaping():
    policy = LivenessPolicy(interval_ms=0)
    assert policy.enabled is False
    # Even a wildly stale connection is kept when reaping is disabled.
    assert policy.evaluate(last_activity=0.0, now=1_000_000.0) is LivenessDecision.KEEP


def test_policy_is_frozen():
    policy = LivenessPolicy()
    with pytest.raises(Exception):
        policy.interval_ms = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LivenessConfig bridge
# ---------------------------------------------------------------------------


def test_config_defaults_disabled():
    cfg = LivenessConfig()
    assert cfg.enabled is False
    policy = cfg.to_policy()
    # Disabled config yields a no-op policy (interval 0 => always KEEP).
    assert policy.enabled is False
    assert policy.evaluate(0.0, 1_000_000.0) is LivenessDecision.KEEP


def test_config_enabled_builds_active_policy():
    cfg = LivenessConfig(enabled=True, interval_ms=5_000, missed_beats_before_reap=3)
    policy = cfg.to_policy()
    assert policy.enabled is True
    assert policy.interval_ms == 5_000
    assert policy.missed_beats_before_reap == 3
    # deadline = 0 + 5 * 3 = 15s.
    assert policy.evaluate(0.0, 16.0) is LivenessDecision.REAP
    assert policy.evaluate(0.0, 10.0) is LivenessDecision.KEEP


def test_config_invalid_values_raise():
    with pytest.raises(ValueError):
        LivenessConfig(interval_ms=-1)
    with pytest.raises(ValueError):
        LivenessConfig(missed_beats_before_reap=0)


def test_config_enabled_with_zero_interval_raises():
    # Contradictory: enabled=True but interval_ms=0 would silently no-op.
    with pytest.raises(ValueError):
        LivenessConfig(enabled=True, interval_ms=0)


def test_config_round_trip_dict():
    cfg = LivenessConfig(enabled=True, interval_ms=20_000, missed_beats_before_reap=4)
    data = cfg.to_dict()
    assert data == {
        "enabled": True,
        "interval_ms": 20_000,
        "missed_beats_before_reap": 4,
    }
    rebuilt = LivenessConfig.from_dict(data)
    assert rebuilt == cfg


def test_config_from_dict_tolerates_none():
    assert LivenessConfig.from_dict(None) == LivenessConfig()


def test_gateway_config_exposes_liveness():
    from praisonaiagents.gateway import GatewayConfig

    gw = GatewayConfig()
    assert isinstance(gw.liveness, LivenessConfig)
    assert "liveness" in gw.to_dict()


def test_gateway_config_from_yaml_parses_liveness():
    from praisonaiagents.gateway import MultiChannelGatewayConfig

    cfg = MultiChannelGatewayConfig.from_dict(
        {
            "gateway": {
                "liveness": {
                    "enabled": True,
                    "interval_ms": 15_000,
                    "missed_beats_before_reap": 2,
                }
            }
        }
    )
    assert cfg.gateway.liveness.enabled is True
    assert cfg.gateway.liveness.interval_ms == 15_000
    assert cfg.gateway.liveness.missed_beats_before_reap == 2
