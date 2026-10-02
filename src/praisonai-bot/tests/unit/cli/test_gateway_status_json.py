"""Tests for the machine-readable ``gateway status --json`` snapshot and the
real (non-hardcoded) version reported by ``/info`` and MCP ``serverInfo`` (#5363).
"""

import json

import pytest
import typer

from praisonai_bot.cli.commands import gateway as gateway_cmd
from praisonai_bot.gateway.server import _installed_gateway_version


def test_installed_version_is_not_hardcoded():
    version = _installed_gateway_version()
    assert version
    assert version != "1.0.0"


def test_build_status_snapshot_merges_health_and_info(monkeypatch):
    health = {
        "status": "healthy",
        "uptime": 3600.0,
        "sessions": 3,
        "clients": 2,
        "agents": 1,
        "channels": {"telegram": {"running": True}},
        "degraded_owners": [],
        "applied_config_revision": "a1b2c3d4e5f6",
        "on_disk_config_revision": "a1b2c3d4e5f6",
        "config_drift": False,
        "pressure": {"outbox_depth": 0, "dlq": 0, "dead_targets": 0},
    }
    info = {"version": "2.3.4", "protocol_version": 7}

    def fake_fetch(host, port, path, timeout=5.0):
        return health if path == "/health" else info

    monkeypatch.setattr(gateway_cmd, "_fetch_gateway_json", fake_fetch)
    monkeypatch.setattr(
        "praisonai_bot.daemon.get_daemon_status",
        lambda: {"platform": "linux", "installed": True, "running": True, "pid": 42},
    )

    snap = gateway_cmd._build_status_snapshot("127.0.0.1", 8765)

    assert snap["reachable"] is True
    assert snap["version"] == "2.3.4"
    assert snap["protocol_version"] == 7
    assert snap["uptime_s"] == 3600.0
    assert snap["active_sessions"] == 3
    assert snap["clients"] == 2
    assert snap["channels"] == {"telegram": {"running": True}}
    assert snap["degraded"] == []
    assert snap["applied_config_revision"] == "a1b2c3d4e5f6"
    assert snap["config_drift"] is False
    assert snap["delivery"] == {"outbox_depth": 0, "dlq": 0, "dead_targets": 0}
    assert snap["daemon"]["running"] is True


def test_build_status_snapshot_unreachable(monkeypatch):
    monkeypatch.setattr(
        gateway_cmd, "_fetch_gateway_json", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "praisonai_bot.daemon.get_daemon_status",
        lambda: {"platform": "linux", "installed": False, "running": False},
    )

    snap = gateway_cmd._build_status_snapshot("127.0.0.1", 8765)
    assert snap["reachable"] is False


def test_status_json_emits_snapshot_and_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        gateway_cmd,
        "_build_status_snapshot",
        lambda host, port: {"reachable": True, "version": "9.9.9"},
    )

    with pytest.raises(typer.Exit) as excinfo:
        gateway_cmd.gateway_status(
            host="127.0.0.1", port=8765, config=None,
            daemon_only=False, deep=False, probe=False, json_output=True,
        )
    assert excinfo.value.exit_code == 0

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["reachable"] is True
    assert payload["version"] == "9.9.9"


def test_status_json_unreachable_exits_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(
        gateway_cmd,
        "_build_status_snapshot",
        lambda host, port: {"reachable": False},
    )

    with pytest.raises(typer.Exit) as excinfo:
        gateway_cmd.gateway_status(
            host="127.0.0.1", port=8765, config=None,
            daemon_only=False, deep=False, probe=False, json_output=True,
        )
    assert excinfo.value.exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reachable"] is False


def test_resolve_auth_token_prefers_env(monkeypatch):
    monkeypatch.setenv("GATEWAY_AUTH_TOKEN", "env-token")
    assert gateway_cmd._resolve_gateway_auth_token() == "env-token"


def test_resolve_auth_token_falls_back_to_persisted_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\nOTHER=1\nGATEWAY_AUTH_TOKEN=\"persisted-token\"\n"
    )
    monkeypatch.setenv("PRAISONAI_ENV_FILE", str(env_file))
    assert gateway_cmd._resolve_gateway_auth_token() == "persisted-token"


def test_resolve_auth_token_missing_returns_empty(monkeypatch, tmp_path):
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("PRAISONAI_ENV_FILE", str(tmp_path / "does-not-exist.env"))
    assert gateway_cmd._resolve_gateway_auth_token() == ""


def test_snapshot_signals_version_unavailable_when_info_unreachable(monkeypatch):
    health = {"status": "healthy", "uptime": 1.0}

    def fake_fetch(host, port, path, timeout=5.0):
        return health if path == "/health" else None

    monkeypatch.setattr(gateway_cmd, "_fetch_gateway_json", fake_fetch)
    monkeypatch.setattr(
        "praisonai_bot.daemon.get_daemon_status",
        lambda: {"platform": "linux", "installed": True, "running": True},
    )

    snap = gateway_cmd._build_status_snapshot("127.0.0.1", 8765)
    assert snap["reachable"] is True
    assert snap.get("version") is None
    assert snap["version_unavailable"] == "info_unreachable"
