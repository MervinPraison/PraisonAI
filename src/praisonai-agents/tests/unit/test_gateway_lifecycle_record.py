"""Unit tests for the durable process-lifecycle primitives (Issue #4603).

Covers the pure, zero-I/O core seam that lets a hosted gateway detect an
unclean/OOM death of its *previous* process at boot, classify memory/disk
pressure for the health surface, and run a restart-loop breaker whose events
survive the restart it guards:

* :class:`LifecycleRecord` (JSON round-trip),
* :func:`classify_unclean_exit`,
* :func:`classify_resource_pressure`, and
* :class:`PersistentRestartLoopGuard` over a :class:`RestartStoreProtocol`.
"""

from typing import List

import pytest

from praisonaiagents.gateway import (
    LifecycleRecord,
    PersistentRestartLoopGuard,
    RestartStoreProtocol,
    classify_resource_pressure,
    classify_unclean_exit,
)


# ── LifecycleRecord round-trip ──


def test_record_round_trips_through_dict():
    rec = LifecycleRecord(
        phase="running",
        exit_kind="unclean",
        suspected_oom=True,
        last_mem_fraction=0.92,
        restart_events=[1.0, 2.0, 3.0],
    )
    back = LifecycleRecord.from_dict(rec.to_dict())
    assert back == rec


def test_from_dict_tolerates_none_and_junk():
    assert LifecycleRecord.from_dict(None) == LifecycleRecord()
    junk = LifecycleRecord.from_dict(
        {"phase": "bogus", "exit_kind": "nope", "restart_events": "x", "last_mem_fraction": "y"}
    )
    assert junk.phase == "running"
    assert junk.exit_kind == "unknown"
    assert junk.restart_events == []
    assert junk.last_mem_fraction is None


def test_from_dict_filters_non_numeric_events():
    rec = LifecycleRecord.from_dict({"restart_events": [1.0, "bad", 3.0, None]})
    assert rec.restart_events == [1.0, 3.0]


# ── classify_unclean_exit ──


def test_no_prior_record_is_unknown():
    rec = classify_unclean_exit(None)
    assert rec.exit_kind == "unknown"
    assert rec.phase == "running"
    assert rec.suspected_oom is False


def test_prior_exited_is_clean():
    prev = LifecycleRecord(phase="exited", exit_kind="clean")
    rec = classify_unclean_exit(prev)
    assert rec.exit_kind == "clean"
    assert rec.phase == "running"


def test_prior_running_is_unclean():
    prev = LifecycleRecord(phase="running", last_mem_fraction=0.5)
    rec = classify_unclean_exit(prev)
    assert rec.exit_kind == "unclean"
    assert rec.suspected_oom is False


def test_prior_running_high_mem_is_suspected_oom():
    prev = LifecycleRecord(phase="running", last_mem_fraction=0.95)
    rec = classify_unclean_exit(prev, oom_fraction=0.9)
    assert rec.exit_kind == "unclean"
    assert rec.suspected_oom is True


def test_prior_draining_is_unclean():
    prev = LifecycleRecord(phase="draining")
    rec = classify_unclean_exit(prev)
    assert rec.exit_kind == "unclean"


def test_restart_events_carry_forward():
    prev = LifecycleRecord(phase="running", restart_events=[1.0, 2.0])
    rec = classify_unclean_exit(prev)
    assert rec.restart_events == [1.0, 2.0]


# ── classify_resource_pressure ──


def test_pressure_missing_signals_are_unknown_not_ok():
    p = classify_resource_pressure()
    assert p == {"memory": "unknown", "disk": "unknown"}


def test_pressure_memory_ladder():
    assert classify_resource_pressure(mem_fraction=0.1)["memory"] == "ok"
    assert classify_resource_pressure(mem_fraction=0.8)["memory"] == "elevated"
    assert classify_resource_pressure(mem_fraction=0.95)["memory"] == "critical"


def test_pressure_disk_ladder():
    assert classify_resource_pressure(disk_free_mb=100, disk_min_free_mb=512)["disk"] == "critical"
    assert classify_resource_pressure(disk_free_mb=700, disk_min_free_mb=512)["disk"] == "elevated"
    assert classify_resource_pressure(disk_free_mb=5000, disk_min_free_mb=512)["disk"] == "ok"


# ── PersistentRestartLoopGuard ──


class _FakeStore:
    """In-memory RestartStoreProtocol double."""

    def __init__(self, initial: List[float] = None):
        self.data: List[float] = list(initial or [])
        self.raise_on_save = False

    def load_events(self) -> List[float]:
        return list(self.data)

    def save_events(self, events: List[float]) -> None:
        if self.raise_on_save:
            raise IOError("boom")
        self.data = list(events)


def test_store_double_satisfies_protocol():
    assert isinstance(_FakeStore(), RestartStoreProtocol)


def test_guard_persists_events_on_record():
    store = _FakeStore()
    guard = PersistentRestartLoopGuard(store, max_restarts=3, window_seconds=3600)
    assert guard.record(now=1.0) is False
    assert guard.record(now=2.0) is False
    assert guard.record(now=3.0) is True
    assert store.data == [1.0, 2.0, 3.0]


def test_guard_reloads_persisted_events_across_boots():
    store = _FakeStore()
    g1 = PersistentRestartLoopGuard(store, max_restarts=3, window_seconds=1e12)
    g1.record(now=1.0)
    g1.record(now=2.0)
    # A fresh guard (new process) reloads history and is one restart from tripping.
    g2 = PersistentRestartLoopGuard(store, max_restarts=3, window_seconds=1e12)
    assert g2.tripped(now=3.0) is False
    assert g2.record(now=3.0) is True


def test_guard_reset_clears_store():
    store = _FakeStore([1.0, 2.0])
    guard = PersistentRestartLoopGuard(store, max_restarts=2, window_seconds=1e12)
    guard.reset()
    assert store.data == []


def test_guard_survives_store_failure():
    store = _FakeStore()
    store.raise_on_save = True
    guard = PersistentRestartLoopGuard(store, max_restarts=2, window_seconds=1e12)
    # A failing store must not crash the breaker: it degrades to in-memory.
    assert guard.record(now=1.0) is False
    assert guard.record(now=2.0) is True


def test_guard_load_failure_falls_back_to_empty():
    class _Broken:
        def load_events(self):
            raise IOError("nope")

        def save_events(self, events):
            pass

    guard = PersistentRestartLoopGuard(_Broken(), max_restarts=2, window_seconds=1e12)
    assert guard.record(now=1.0) is False
