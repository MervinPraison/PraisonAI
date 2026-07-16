#!/usr/bin/env python3
"""Tests for config hot-reload observability in health() (Issue #3049).

Covers the core contract (`ReloadStatus`, `compute_config_revision`) and the
wrapper's population of reload outcome / applied-config revision / watcher
liveness in `WebSocketGateway.health()`.
"""

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonaiagents.gateway import ReloadStatus, compute_config_revision
from praisonai_bot.gateway.server import WebSocketGateway


# ── Core: compute_config_revision ──────────────────────────────────────────

def test_revision_stable_across_key_ordering():
    """Same logical config -> same revision regardless of key order."""
    a = compute_config_revision({"b": 1, "a": {"y": 2, "x": 3}})
    b = compute_config_revision({"a": {"x": 3, "y": 2}, "b": 1})
    assert a == b


def test_revision_changes_with_content():
    """Different config content -> different revision."""
    a = compute_config_revision({"a": 1})
    b = compute_config_revision({"a": 2})
    assert a != b


def test_revision_empty_is_stable_sentinel():
    """None/empty config both hash to the same stable sentinel."""
    assert compute_config_revision(None) == compute_config_revision({})


def test_revision_unhashable_does_not_raise():
    """A config with non-JSON values still hashes rather than raising."""
    class Weird:
        pass

    rev = compute_config_revision({"x": Weird()})
    assert isinstance(rev, str) and len(rev) == 12


# ── Core: ReloadStatus ─────────────────────────────────────────────────────

def test_reload_status_defaults():
    r = ReloadStatus()
    assert r.watcher == "disabled"
    assert r.last_result == "never"
    assert r.to_dict() == {
        "watcher": "disabled",
        "last_result": "never",
        "last_at": None,
        "changed_paths": [],
        "error": None,
    }


def test_reload_status_to_dict_serializable():
    r = ReloadStatus(
        watcher="active",
        last_result="ok",
        last_at=123.0,
        changed_paths=("channels.telegram",),
    )
    d = r.to_dict()
    assert d["watcher"] == "active"
    assert d["changed_paths"] == ["channels.telegram"]


# ── Wrapper: health() surfaces reload state ────────────────────────────────

def test_health_no_reload_fields_without_config():
    """Gateway started without a config file -> no reload/revision fields."""
    gw = WebSocketGateway()
    health = gw.health()
    assert "reload" not in health
    assert "applied_config_revision" not in health


def test_health_reports_applied_revision_and_watcher():
    """With a config path + applied revision, health surfaces both."""
    gw = WebSocketGateway()
    gw._config_path = "/tmp/does-not-exist-gateway.yaml"
    gw._applied_config_revision = "abc123abc123"
    gw._reload_watcher_active = True
    health = gw.health()
    assert health["applied_config_revision"] == "abc123abc123"
    assert health["reload"]["watcher"] == "active"
    # On-disk read fails for a missing file -> no on_disk revision, no crash.
    assert "on_disk_config_revision" not in health


def test_record_reload_status_failure():
    """A failed reload is recorded so it's visible in health()."""
    gw = WebSocketGateway()
    gw._reload_watcher_active = True
    gw._record_reload_status("failed", error="channels.telegram.token: required")
    d = gw._reload_status.to_dict()
    assert d["last_result"] == "failed"
    assert d["watcher"] == "active"
    assert "token" in d["error"]
    assert d["last_at"] is not None


def test_reload_failure_recorded_via_locked(tmp_path):
    """_reload_config_locked records 'failed' when config is invalid."""
    gw = WebSocketGateway()
    bad = tmp_path / "gateway.yaml"
    # Parses to a bare string (non-dict) -> load_gateway_config raises ValueError.
    bad.write_text("just a scalar, not a mapping")
    asyncio.run(gw._reload_config_locked(str(bad)))
    assert gw._reload_status is not None
    assert gw._reload_status.last_result == "failed"
    assert gw._config_path == str(bad)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
