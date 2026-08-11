#!/usr/bin/env python3
"""Tests for the gateway idle/scale-to-zero + epoch-aware drain wiring (#3021).

Covers ``WebSocketGateway`` consuming the pure core lifecycle policies:
``ScaleToZeroPolicy`` (idle-quiesce), ``DrainMarkerPolicy`` + ``current_epoch``
(epoch-aware external drain), and the ``RestartLoopGuard`` crash-loop breaker —
all opt-in via a ``lifecycle:`` config block so always-on gateways are unchanged.
"""

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonai_bot.gateway.server import WebSocketGateway


def _make_gateway():
    return WebSocketGateway()


def test_lifecycle_off_by_default():
    gw = _make_gateway()
    assert gw._idle_policy is None
    assert gw._drain_marker_policy is None
    assert gw._restart_loop_guard is None
    # No lifecycle key in health when nothing is configured.
    assert "lifecycle" not in gw.health()


def test_configure_scale_to_zero():
    gw = _make_gateway()
    gw._configure_lifecycle(
        {"scale_to_zero": {"enabled": True, "idle_minutes": 7, "wake_url": "https://x/wake"}}
    )
    assert gw._idle_policy is not None
    assert gw._idle_policy.idle_timeout_minutes == 7.0
    assert gw._idle_policy.wake_url == "https://x/wake"
    assert gw.health()["lifecycle"]["scale_to_zero"] is True


def test_configure_scale_to_zero_disabled_when_flag_off():
    gw = _make_gateway()
    gw._configure_lifecycle({"scale_to_zero": {"enabled": False, "idle_minutes": 7}})
    assert gw._idle_policy is None


def test_configure_restart_loop_guard():
    gw = _make_gateway()
    gw._configure_lifecycle(
        {"restart_loop_guard": {"max_restarts": 5, "window_seconds": 120}}
    )
    assert gw._restart_loop_guard is not None
    assert gw._restart_loop_guard.max_restarts == 5
    assert gw._restart_loop_guard.window_seconds == 120.0


def test_probe_idle_facts_empty():
    gw = _make_gateway()
    running, _last_ts, has_bg = gw._probe_idle_facts()
    assert running == 0
    assert has_bg is False


def test_quiesce_and_wake_are_idempotent():
    gw = _make_gateway()

    async def _run():
        await gw._quiesce("test")
        assert gw._is_dormant is True
        # Second quiesce is a no-op.
        await gw._quiesce("again")
        assert gw._is_dormant is True
        await gw.wake()
        assert gw._is_dormant is False
        # Second wake is a no-op.
        await gw.wake()
        assert gw._is_dormant is False

    asyncio.run(_run())


def test_on_quiesce_driver_invoked():
    gw = _make_gateway()
    calls = []
    gw._on_quiesce = lambda: calls.append(1)

    asyncio.run(gw._quiesce("idle"))
    assert calls == [1]


def test_drain_marker_current_epoch_honoured(tmp_path):
    gw = _make_gateway()
    marker = tmp_path / "gateway.drain"
    gw._configure_lifecycle({"drain": {"marker_path": str(marker)}})
    assert gw._drain_marker_policy is not None
    # Force a deterministic epoch so we don't depend on /proc availability.
    gw._instantiation_epoch = "epoch-A"
    marker.write_text(json.dumps({"action": "drain", "epoch": "epoch-A"}))

    read = gw._read_drain_marker()
    assert gw._drain_marker_policy.drain_requested(
        read, gw._instantiation_epoch, 0.0
    ) is True


def test_drain_marker_stale_epoch_ignored(tmp_path):
    gw = _make_gateway()
    marker = tmp_path / "gateway.drain"
    gw._configure_lifecycle({"drain": {"marker_path": str(marker)}})
    gw._instantiation_epoch = "epoch-current"
    # A marker left by a prior instantiation (survived a reboot on a durable volume).
    marker.write_text(json.dumps({"action": "drain", "epoch": "epoch-old"}))

    read = gw._read_drain_marker()
    assert gw._drain_marker_policy.drain_requested(
        read, gw._instantiation_epoch, 0.0
    ) is False


def test_read_drain_marker_absent_returns_none(tmp_path):
    gw = _make_gateway()
    gw._drain_marker_path = str(tmp_path / "missing.drain")
    assert gw._read_drain_marker() is None


def test_merge_lifecycle_overrides_from_cli():
    gw = _make_gateway()
    gw._scale_to_zero_override = True
    gw._idle_minutes_override = 3.0
    gw._drain_marker_override = "/data/g.drain"
    merged = gw._merge_lifecycle_overrides(None, None)
    assert merged["scale_to_zero"]["enabled"] is True
    assert merged["scale_to_zero"]["idle_minutes"] == 3.0
    assert merged["drain"]["marker_path"] == "/data/g.drain"


def test_merge_lifecycle_overrides_noop_without_cli():
    gw = _make_gateway()
    assert gw._merge_lifecycle_overrides(None, None) is None
    original = {"scale_to_zero": {"enabled": True}}
    assert gw._merge_lifecycle_overrides(original, None) is original
