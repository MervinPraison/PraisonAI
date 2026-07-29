#!/usr/bin/env python3
"""Tests for the gateway event-loop liveness watchdog wiring (#3410).

Covers ``WebSocketGateway`` building and arming the pure core primitive
``LoopWatchdog`` / ``LoopWatchdogPolicy`` (Issue #3385) around its serving
loop — opt-in via a ``gateway.watchdog`` config block (or the CLI
``--watchdog`` flag), so always-on gateways keep their exact behaviour.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonai_bot.gateway.server import WebSocketGateway


def _make_gateway():
    return WebSocketGateway()


def test_watchdog_off_by_default():
    gw = _make_gateway()
    assert gw._watchdog is None
    # No watchdog key in health when nothing is configured.
    assert "watchdog" not in gw.health()


def test_configure_watchdog_disabled_when_flag_off():
    gw = _make_gateway()
    gw._configure_watchdog({"enabled": False, "liveness_interval": 5})
    assert gw._watchdog is None


def test_configure_watchdog_none_is_noop():
    gw = _make_gateway()
    gw._configure_watchdog(None)
    assert gw._watchdog is None


def test_configure_watchdog_enabled():
    gw = _make_gateway()
    gw._configure_watchdog(
        {"enabled": True, "liveness_interval": 3, "liveness_strikes": 4}
    )
    assert gw._watchdog is not None
    assert gw._watchdog.policy.probe_interval_s == 3.0
    assert gw._watchdog.policy.missed_probes_before_wedged == 4
    # Approx wedge budget: interval * strikes.
    assert gw._watchdog.policy.wedge_after_s == 12.0
    hb = gw.health()["watchdog"]
    assert hb["enabled"] is True
    assert hb["armed"] is False
    assert hb["wedge_after_s"] == 12.0


def test_configure_watchdog_string_truthy():
    gw = _make_gateway()
    gw._configure_watchdog({"enabled": "true"})
    assert gw._watchdog is not None


def test_configure_watchdog_defaults():
    gw = _make_gateway()
    gw._configure_watchdog({"enabled": True})
    assert gw._watchdog is not None
    assert gw._watchdog.policy.probe_interval_s == 5.0
    assert gw._watchdog.policy.missed_probes_before_wedged == 3


def test_configure_watchdog_invalid_disables():
    gw = _make_gateway()
    # A non-positive interval is rejected by LoopWatchdogPolicy; the wiring
    # must fail closed (no watchdog) rather than raise on start.
    gw._configure_watchdog({"enabled": True, "liveness_interval": 0})
    assert gw._watchdog is None


def test_merge_watchdog_overrides_enable():
    gw = _make_gateway()
    gw._watchdog_override = True
    merged = gw._merge_watchdog_overrides(None)
    assert merged["enabled"] is True


def test_merge_watchdog_overrides_timeout_derives_interval():
    gw = _make_gateway()
    gw._watchdog_override = True
    gw._watchdog_timeout_override = 15.0
    merged = gw._merge_watchdog_overrides(None)
    assert merged["enabled"] is True
    assert merged["liveness_strikes"] == 3
    assert merged["liveness_interval"] == 5.0


def test_merge_watchdog_overrides_no_flags_passthrough():
    gw = _make_gateway()
    original = {"enabled": True, "liveness_interval": 7}
    assert gw._merge_watchdog_overrides(original) is original


def test_merge_watchdog_overrides_cli_wins_over_yaml():
    gw = _make_gateway()
    gw._watchdog_override = True
    merged = gw._merge_watchdog_overrides({"enabled": False})
    assert merged["enabled"] is True


def test_arm_and_disarm_are_safe_without_watchdog():
    gw = _make_gateway()
    # No watchdog configured: both are no-ops and must not raise.
    gw._arm_watchdog()
    gw._disarm_watchdog()
    assert gw._watchdog is None


def test_disarm_after_configure_is_safe():
    gw = _make_gateway()
    gw._configure_watchdog({"enabled": True})
    # Never armed (no running loop); disarm must be safe.
    gw._disarm_watchdog()
    assert gw._watchdog is not None
    assert gw._watchdog.armed is False


# ── Active Typer CLI surface (#3410) ──
# Guards against the flags being defined only on the legacy argparse parser
# while the real ``praisonai gateway start`` entrypoint silently drops them.


def test_typer_start_exposes_watchdog_flags():
    import typer
    from praisonai_bot.cli.commands.gateway import app

    start = typer.main.get_command(app).get_command(None, "start")
    opts = {name for p in start.params for name in p.opts}
    assert "--watchdog" in opts
    assert "--watchdog-timeout" in opts


def _patch_handler(monkeypatch, captured):
    # ``gateway_start`` imports GatewayHandler lazily from the features module,
    # so patch it there (it is never a ``commands.gateway`` module attribute).
    from praisonai_bot.cli.features import gateway as features_gateway

    class _StubHandler:
        def start(self, **kwargs):
            captured.update(kwargs)
            return 0

    monkeypatch.setattr(features_gateway, "GatewayHandler", _StubHandler)


def test_typer_start_forwards_watchdog_to_handler(monkeypatch):
    from typer.testing import CliRunner
    from praisonai_bot.cli.commands import gateway as gateway_cmd

    captured = {}
    _patch_handler(monkeypatch, captured)

    result = CliRunner().invoke(
        gateway_cmd.app,
        ["start", "--watchdog", "--watchdog-timeout", "20", "--no-preflight"],
    )
    assert result.exit_code == 0
    assert captured.get("watchdog") is True
    assert captured.get("watchdog_timeout") == 20.0


def test_typer_start_watchdog_unset_is_none(monkeypatch):
    from typer.testing import CliRunner
    from praisonai_bot.cli.commands import gateway as gateway_cmd

    captured = {}
    _patch_handler(monkeypatch, captured)

    result = CliRunner().invoke(gateway_cmd.app, ["start", "--no-preflight"])
    assert result.exit_code == 0
    # Unset flag must not clobber a YAML ``gateway.watchdog.enabled: true``.
    assert captured.get("watchdog") is None
    assert captured.get("watchdog_timeout") is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
