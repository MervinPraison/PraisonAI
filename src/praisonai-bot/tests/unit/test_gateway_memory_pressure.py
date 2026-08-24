"""Tests for gateway memory-pressure cache eviction wiring (Issue #3804).

The core planner ``plan_pressure_evictions`` is unit-tested in the core SDK; here
we verify the *wrapper enactor* — ``BotSessionManager.sweep_under_pressure`` and
``warm_sessions`` — plus the concrete stdlib ``CgroupMemoryPressure`` reader.
"""

from __future__ import annotations

import pytest

from praisonai_bot.bots._session import BotSessionManager
from praisonai_bot.gateway.memory_pressure import CgroupMemoryPressure


class _Store:
    """Minimal in-memory SessionStore so sessions count as 'flushed'."""

    def __init__(self):
        self.saved = {}

    def set_chat_history(self, key, history):
        self.saved[key] = list(history)

    def get_chat_history(self, key):
        return list(self.saved.get(key, []))

    def clear_session(self, key):
        self.saved.pop(key, None)


class _Pressure:
    """Scripted MemoryPressureProtocol: fixed budget, decreasing RSS samples."""

    def __init__(self, budget, rss_samples):
        self._budget = budget
        self._rss = list(rss_samples)

    def cgroup_limit_mb(self):
        return self._budget

    def anon_rss_mb(self):
        # First call returns the initial reading; subsequent calls pop the next
        # (simulating RSS dropping as caches are evicted).
        return self._rss.pop(0) if len(self._rss) > 1 else self._rss[0]


def _warm(mgr, key, last_active):
    """Seed a warm in-memory cache with a given LRU timestamp."""
    mgr._histories[key] = [{"role": "user", "content": "hi"}]
    mgr._last_active[key] = last_active


def test_warm_sessions_reports_flushed_when_store_present():
    store = _Store()
    mgr = BotSessionManager(store=store)
    _warm(mgr, "a", 1.0)
    warm = mgr.warm_sessions()
    assert len(warm) == 1
    assert warm[0].session_id == "a"
    assert warm[0].flushed is True
    assert warm[0].in_flight is False


def test_warm_sessions_unflushed_without_store():
    mgr = BotSessionManager(store=None)
    _warm(mgr, "a", 1.0)
    assert mgr.warm_sessions()[0].flushed is False


def test_sweep_evicts_coldest_first_until_within_budget():
    store = _Store()
    mgr = BotSessionManager(store=store)
    _warm(mgr, "cold", 1.0)
    _warm(mgr, "warm", 100.0)
    # Budget 1000 MiB, target = 900. Start at 1000 (over), drop to 850 after the
    # first (coldest) eviction so the sweep stops having shed exactly one cache.
    mp = _Pressure(1000.0, [1000.0, 850.0])
    evicted = mgr.sweep_under_pressure(mp, headroom=0.9)
    assert evicted == 1
    assert "cold" not in mgr._histories   # coldest dropped
    assert "warm" in mgr._histories       # warmest kept


def test_sweep_never_evicts_unflushed_cache():
    mgr = BotSessionManager(store=None)  # no store => nothing rebuildable
    _warm(mgr, "a", 1.0)
    mp = _Pressure(100.0, [1000.0])
    assert mgr.sweep_under_pressure(mp) == 0
    assert "a" in mgr._histories


def test_sweep_never_evicts_in_flight_cache():
    store = _Store()
    mgr = BotSessionManager(store=store)
    _warm(mgr, "a", 1.0)
    mgr._in_flight["a"] = 1  # a live turn is executing
    mp = _Pressure(100.0, [1000.0])
    assert mgr.sweep_under_pressure(mp) == 0
    assert "a" in mgr._histories


def test_sweep_noop_when_no_budget():
    store = _Store()
    mgr = BotSessionManager(store=store)
    _warm(mgr, "a", 1.0)
    mp = _Pressure(None, [1000.0])  # host without a cgroup limit
    assert mgr.sweep_under_pressure(mp) == 0
    assert "a" in mgr._histories


def test_sweep_noop_when_within_budget():
    store = _Store()
    mgr = BotSessionManager(store=store)
    _warm(mgr, "a", 1.0)
    mp = _Pressure(1000.0, [500.0])  # RSS well under 900 target
    assert mgr.sweep_under_pressure(mp) == 0
    assert "a" in mgr._histories


def test_soft_evict_leaves_store_intact():
    store = _Store()
    store.set_chat_history("a", [{"role": "user", "content": "persisted"}])
    mgr = BotSessionManager(store=store)
    _warm(mgr, "a", 1.0)
    assert mgr._soft_evict("a") is True
    assert "a" not in mgr._histories          # in-memory dropped
    assert store.get_chat_history("a")        # durable copy remains


def test_cgroup_reader_degrades_gracefully(monkeypatch):
    reader = CgroupMemoryPressure()

    def _boom(*_a, **_k):
        raise OSError("no cgroup here")

    monkeypatch.setattr("builtins.open", _boom)
    assert reader.cgroup_limit_mb() is None
    assert reader.anon_rss_mb() == 0.0


def test_cgroup_reader_parses_v2_max(tmp_path, monkeypatch):
    reader = CgroupMemoryPressure()
    limit_file = tmp_path / "memory.max"
    limit_file.write_text("536870912\n")  # 512 MiB

    real_open = open

    def _fake_open(path, *a, **k):
        if path == "/sys/fs/cgroup/memory.high":
            raise OSError
        if path == "/sys/fs/cgroup/memory.max":
            return real_open(limit_file, *a, **k)
        raise OSError

    monkeypatch.setattr("builtins.open", _fake_open)
    assert reader.cgroup_limit_mb() == pytest.approx(512.0)


def test_cgroup_reader_v2_unlimited_is_none(tmp_path, monkeypatch):
    reader = CgroupMemoryPressure()
    hi = tmp_path / "memory.high"
    hi.write_text("max\n")
    real_open = open

    def _fake_open(path, *a, **k):
        if path == "/sys/fs/cgroup/memory.high":
            return real_open(hi, *a, **k)
        raise OSError

    monkeypatch.setattr("builtins.open", _fake_open)
    assert reader.cgroup_limit_mb() is None
