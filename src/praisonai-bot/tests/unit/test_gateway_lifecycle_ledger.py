"""Tests for the durable gateway lifecycle ledger wiring (Issue #4603).

The core primitives (``LifecycleRecord`` / ``classify_unclean_exit`` /
``PersistentRestartLoopGuard`` / ``classify_resource_pressure``) are unit-tested
in the core SDK; here we verify the *wrapper mechanism* — the durable sentinel,
the boot classification, the graceful-exit marker, the memory sample, and the
sentinel-backed restart store.
"""

from __future__ import annotations

import json
import os

import pytest

from praisonai_bot.gateway.lifecycle_ledger import (
    LifecycleLedger,
    SentinelRestartStore,
    build_persistent_restart_guard,
    default_sentinel_path,
)


def test_fresh_boot_is_unknown(tmp_path):
    ledger = LifecycleLedger(str(tmp_path / "lifecycle.json"))
    rec = ledger.record_boot()
    assert rec.exit_kind == "unknown"
    assert ledger.last_exit() == {"last_exit": "unknown", "suspected_oom": False}


def test_graceful_stop_marks_clean_and_next_boot_sees_clean(tmp_path):
    path = str(tmp_path / "lifecycle.json")
    ledger = LifecycleLedger(path)
    ledger.record_boot()
    ledger.mark_exited()

    data = json.loads((tmp_path / "lifecycle.json").read_text())
    assert data["phase"] == "exited"
    assert data["exit_kind"] == "clean"

    ledger2 = LifecycleLedger(path)
    rec = ledger2.record_boot()
    assert rec.exit_kind == "clean"


def test_unclean_death_detected_on_next_boot(tmp_path):
    path = str(tmp_path / "lifecycle.json")
    # Process A boots and never marks exited (simulated OOM/SIGKILL).
    ledger_a = LifecycleLedger(path, memory_budget_fraction=0.9)
    ledger_a.record_boot()
    # A high memory sample was folded in by the heartbeat before death.
    from praisonaiagents.gateway import LifecycleRecord

    ledger_a._record = LifecycleRecord(
        phase="running", exit_kind="unknown", last_mem_fraction=0.97,
    )
    ledger_a._write(ledger_a._record)

    # Process B boots and detects the unclean prior exit.
    ledger_b = LifecycleLedger(path, memory_budget_fraction=0.9)
    rec = ledger_b.record_boot()
    assert rec.exit_kind == "unclean"
    assert rec.suspected_oom is True
    assert ledger_b.last_exit() == {"last_exit": "unclean", "suspected_oom": True}


def test_mark_exited_is_ownership_checked(tmp_path, monkeypatch):
    path = str(tmp_path / "lifecycle.json")
    ledger = LifecycleLedger(path)
    ledger.record_boot()
    # Pretend a different pid owns the boot marker: mark_exited must be a no-op.
    ledger._owner_pid = os.getpid() + 1
    ledger.mark_exited()
    data = json.loads((tmp_path / "lifecycle.json").read_text())
    assert data["phase"] == "running"


def test_sample_memory_never_raises(tmp_path):
    ledger = LifecycleLedger(str(tmp_path / "lifecycle.json"))
    ledger.record_boot()
    # Returns a float fraction or None; must not raise on any host.
    frac = ledger.sample_memory()
    assert frac is None or isinstance(frac, float)


def test_pressure_returns_closed_vocabulary(tmp_path):
    ledger = LifecycleLedger(str(tmp_path / "lifecycle.json"))
    p = ledger.pressure()
    assert set(p.keys()) == {"memory", "disk"}
    for v in p.values():
        assert v in ("ok", "elevated", "critical", "unknown")


def test_pressure_disk_ok_on_tmp(tmp_path):
    # A tmp dir on CI has ample headroom; disk should classify ok (not unknown).
    ledger = LifecycleLedger(str(tmp_path / "lifecycle.json"), disk_min_free_mb=1)
    assert ledger.pressure()["disk"] == "ok"


def test_restart_store_shares_sentinel(tmp_path):
    path = str(tmp_path / "lifecycle.json")
    ledger = LifecycleLedger(path)
    ledger.record_boot()
    guard = build_persistent_restart_guard(ledger, max_restarts=3, window_seconds=1e12)
    assert guard.record(now=1.0) is False
    assert guard.record(now=2.0) is False
    assert guard.record(now=3.0) is True

    # The events landed in the shared sentinel and reload in a fresh process.
    ledger2 = LifecycleLedger(path)
    ledger2.record_boot()
    guard2 = build_persistent_restart_guard(ledger2, max_restarts=3, window_seconds=1e12)
    assert guard2.tripped(now=4.0) is True


def test_default_sentinel_path_under_praisonai():
    p = default_sentinel_path()
    assert p.endswith(os.path.join(".praisonai", "gateway", "lifecycle.json"))


def test_corrupt_sentinel_is_tolerated(tmp_path):
    path = tmp_path / "lifecycle.json"
    path.write_text("{not valid json")
    ledger = LifecycleLedger(str(path))
    # A corrupt prior file reads as "no record" -> unknown, never raises.
    rec = ledger.record_boot()
    assert rec.exit_kind == "unknown"
