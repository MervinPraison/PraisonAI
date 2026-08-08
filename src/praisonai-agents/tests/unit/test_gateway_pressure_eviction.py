"""Unit tests for gateway memory-pressure cache eviction (Issue #3804).

Covers the pure, core-side ``plan_pressure_evictions`` planner and the
``WarmSession`` / ``MemoryPressureProtocol`` contracts. The planner names the
coldest (LRU) rebuildable warm session-agent caches to soft-evict before the
kernel OOM-kills the process, while never evicting an in-flight or
not-yet-flushed session.
"""

from praisonaiagents.gateway import (
    MemoryPressureProtocol,
    WarmSession,
    plan_pressure_evictions,
)


def _warm(sid, last_activity, *, in_flight=False, flushed=True):
    return WarmSession(
        session_id=sid,
        last_activity=last_activity,
        in_flight=in_flight,
        flushed=flushed,
    )


def test_within_budget_evicts_nothing():
    warm = [_warm("a", 1.0), _warm("b", 2.0)]
    assert plan_pressure_evictions(1000.0, 500.0, warm) == []


def test_unknown_budget_is_noop():
    warm = [_warm("a", 1.0)]
    assert plan_pressure_evictions(None, 9999.0, warm) == []


def test_nonpositive_budget_is_noop():
    warm = [_warm("a", 1.0)]
    assert plan_pressure_evictions(0.0, 9999.0, warm) == []
    assert plan_pressure_evictions(-100.0, 9999.0, warm) == []


def test_evicts_coldest_first_under_pressure():
    warm = [
        _warm("hot", 300.0),
        _warm("cold", 10.0),
        _warm("mid", 100.0),
    ]
    # rss (950) above 90% of budget (900) -> shed evictable, LRU first.
    victims = plan_pressure_evictions(1000.0, 950.0, warm)
    assert victims == ["cold", "mid", "hot"]


def test_skips_in_flight_session():
    warm = [
        _warm("cold-busy", 10.0, in_flight=True),
        _warm("warm-idle", 200.0),
    ]
    victims = plan_pressure_evictions(1000.0, 999.0, warm)
    assert victims == ["warm-idle"]


def test_skips_unflushed_session():
    warm = [
        _warm("cold-unflushed", 10.0, flushed=False),
        _warm("warm-flushed", 200.0),
    ]
    victims = plan_pressure_evictions(1000.0, 999.0, warm)
    assert victims == ["warm-flushed"]


def test_no_evictable_returns_empty():
    warm = [
        _warm("busy", 10.0, in_flight=True),
        _warm("unflushed", 20.0, flushed=False),
    ]
    assert plan_pressure_evictions(1000.0, 999.0, warm) == []


def test_empty_registry_returns_empty():
    assert plan_pressure_evictions(1000.0, 999.0, []) == []


def test_headroom_ratio_controls_trigger():
    warm = [_warm("a", 1.0)]
    # rss 800 is within 90% (900) -> no eviction, but breaches 70% (700).
    assert plan_pressure_evictions(1000.0, 800.0, warm) == []
    assert plan_pressure_evictions(1000.0, 800.0, warm, headroom_ratio=0.7) == ["a"]


def test_invalid_headroom_ratio_falls_back_to_default():
    warm = [_warm("a", 1.0)]
    # Out-of-range ratios fall back to 0.9; rss 950 > 900 -> evict.
    assert plan_pressure_evictions(1000.0, 950.0, warm, headroom_ratio=0.0) == ["a"]
    assert plan_pressure_evictions(1000.0, 950.0, warm, headroom_ratio=5.0) == ["a"]


def test_bad_numbers_are_noop():
    warm = [_warm("a", 1.0)]
    assert plan_pressure_evictions("nope", 999.0, warm) == []  # type: ignore[arg-type]
    assert plan_pressure_evictions(1000.0, "nope", warm) == []  # type: ignore[arg-type]


def test_stable_tiebreak_by_session_id():
    warm = [_warm("b", 50.0), _warm("a", 50.0)]
    victims = plan_pressure_evictions(1000.0, 999.0, warm)
    assert victims == ["a", "b"]


def test_warm_session_defaults():
    s = WarmSession(session_id="x")
    assert s.last_activity == 0.0
    assert s.in_flight is False
    assert s.flushed is True


def test_memory_pressure_protocol_conformance():
    class _Probe:
        def cgroup_limit_mb(self):
            return 512.0

        def anon_rss_mb(self):
            return 128.0

    assert isinstance(_Probe(), MemoryPressureProtocol)
