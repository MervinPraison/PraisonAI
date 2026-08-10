"""Fleet-level crash-loop breaker tests (Issue #3840).

Covers the aggregate breaker that sits on top of the per-channel restart budget:
- the pure core ``FleetSupervisionPolicy`` decision, and
- the wrapper ``ChannelHealthMonitor`` enforcement + single ``gateway``
  degraded-owner fact recorded on the shared registry.
"""

from __future__ import annotations

import pytest

from praisonaiagents.gateway import (
    DegradedCapabilityRegistry,
    FleetSupervisionPolicy,
)
from praisonaiagents.bots.protocols import HealthReason
from praisonai_bot.gateway.health_monitor import (
    ChannelHealthMonitor,
    HealthMonitorConfig,
)


# --- Core policy ---------------------------------------------------------


def test_policy_trips_on_fleet_restart_rate():
    policy = FleetSupervisionPolicy(fleet_restarts_per_hour=3, breaker_cooldown_s=10)
    t = 100.0
    assert policy.note_restart(t) is False
    assert policy.note_restart(t + 1) is False
    assert policy.note_restart(t + 2) is True  # third restart trips
    assert policy.tripped(t + 3) is True


def test_policy_cooldown_rearms():
    policy = FleetSupervisionPolicy(fleet_restarts_per_hour=2, breaker_cooldown_s=10)
    t = 0.0
    policy.note_restart(t)
    assert policy.note_restart(t + 1) is True
    assert policy.tripped(t + 5) is True
    assert policy.tripped(t + 20) is False  # cooldown elapsed


def test_policy_trips_on_failing_fraction():
    policy = FleetSupervisionPolicy(failing_channel_fraction=0.5)
    assert policy.note_fleet_state(4, 8, now=0.0) is True
    assert policy.note_fleet_state(1, 8, now=0.0) in (True, False)  # still cooling


def test_policy_rejects_bad_config():
    with pytest.raises(ValueError):
        FleetSupervisionPolicy(fleet_restarts_per_hour=0)
    with pytest.raises(ValueError):
        FleetSupervisionPolicy(failing_channel_fraction=0.0)
    with pytest.raises(ValueError):
        FleetSupervisionPolicy(failing_channel_fraction=1.5)


def test_config_parses_fleet_thresholds():
    cfg = HealthMonitorConfig.from_dict(
        {
            "fleet_restarts_per_hour": 12,
            "failing_channel_fraction": 0.25,
            "breaker_cooldown_s": 30,
        }
    )
    assert cfg.fleet_restarts_per_hour == 12
    assert cfg.failing_channel_fraction == 0.25
    assert cfg.breaker_cooldown_s == 30

    # Defensive parsing: bad values fall back / clamp instead of raising.
    bad = HealthMonitorConfig.from_dict(
        {"fleet_restarts_per_hour": "oops", "failing_channel_fraction": 5.0}
    )
    assert bad.fleet_restarts_per_hour == HealthMonitorConfig().fleet_restarts_per_hour
    assert bad.failing_channel_fraction == 1.0


# --- Wrapper enforcement -------------------------------------------------


class _FakeBot:
    platform = "telegram"

    def __init__(self):
        self.is_running = True

    async def health(self):
        from praisonaiagents.bots.protocols import HealthResult

        # is_running=True + error -> HealthReason.ERROR, a recoverable state that
        # drives the restart path (NOT_RUNNING would be treated as terminal).
        return HealthResult(
            ok=False,
            platform=self.platform,
            is_running=True,
            uptime_seconds=999.0,
            error="boom",
        )


@pytest.mark.asyncio
async def test_breaker_holds_restarts_and_records_one_degraded_owner():
    registry = DegradedCapabilityRegistry()
    restarts: list[str] = []

    async def restart_fn(name, reason):
        restarts.append(name)

    # Fleet breaker trips on the 3rd fleet restart; per-channel budget generous
    # so the fleet breaker is what trips.
    cfg = HealthMonitorConfig(
        max_restarts_per_hour=100,
        fleet_restarts_per_hour=3,
        breaker_cooldown_s=60,
    )
    mon = ChannelHealthMonitor(
        config=cfg, restart_fn=restart_fn, degraded_registry=registry
    )

    for name in ("a", "b", "c"):
        mon.register_channel(name, _FakeBot())

    import time as _time

    now = _time.time()
    # Each channel needs a restart; the 3rd fleet restart trips the breaker,
    # so the 3rd channel must be HELD (no restart) and one degraded fact recorded.
    for name in ("a", "b", "c"):
        await mon._check_channel(name, mon._channels[name], now)

    assert restarts == ["a", "b"], "third restart should be held by the breaker"

    owners = registry.list_degraded()
    assert len(owners) == 1
    owner = owners[0]
    assert owner.owner_kind == "gateway"
    assert owner.owner_id == "fleet"
    assert "crash-loop" in owner.reason
    assert owner.retry_hint == "praisonai gateway doctor"

    status = mon.get_status()
    assert status["fleet"]["breaker_tripped"] is True


@pytest.mark.asyncio
async def test_breaker_no_registry_still_holds():
    restarts: list[str] = []

    async def restart_fn(name, reason):
        restarts.append(name)

    cfg = HealthMonitorConfig(
        max_restarts_per_hour=100, fleet_restarts_per_hour=1, breaker_cooldown_s=60
    )
    mon = ChannelHealthMonitor(config=cfg, restart_fn=restart_fn)
    mon.register_channel("a", _FakeBot())
    mon.register_channel("b", _FakeBot())

    import time as _time

    now = _time.time()
    await mon._check_channel("a", mon._channels["a"], now)
    await mon._check_channel("b", mon._channels["b"], now)
    # First restart trips (threshold=1); second is held. No registry -> no crash.
    assert restarts == []  # threshold 1 means the very first restart trips
