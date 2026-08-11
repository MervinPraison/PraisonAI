"""Unit tests for the pure ``RestartLoopGuard`` crash-loop predicate (Issue #3021).

Covers the core-side rolling-window guard that trips when a gateway restarts
too many times inside a short window, so the wrapper runtimes can stop
auto-resuming an offending session while still serving real inbound.
"""

import pytest

from praisonaiagents.gateway import RestartLoopGuard


def test_does_not_trip_below_threshold():
    guard = RestartLoopGuard(max_restarts=3, window_seconds=60)
    assert guard.record(now=0.0) is False
    assert guard.record(now=1.0) is False


def test_trips_at_threshold_within_window():
    guard = RestartLoopGuard(max_restarts=3, window_seconds=60)
    assert guard.record(now=0.0) is False
    assert guard.record(now=10.0) is False
    assert guard.record(now=20.0) is True


def test_events_age_out_of_window():
    guard = RestartLoopGuard(max_restarts=3, window_seconds=60)
    guard.record(now=0.0)
    guard.record(now=10.0)
    # This restart is >60s after the first two, which have aged out.
    assert guard.record(now=200.0) is False


def test_tripped_reflects_current_window_without_recording():
    guard = RestartLoopGuard(max_restarts=2, window_seconds=30)
    guard.record(now=0.0)
    guard.record(now=5.0)
    assert guard.tripped(now=6.0) is True
    # A later probe outside the window sees the burst has gone quiet.
    assert guard.tripped(now=100.0) is False


def test_reset_clears_history():
    guard = RestartLoopGuard(max_restarts=2, window_seconds=60)
    guard.record(now=0.0)
    guard.record(now=1.0)
    assert guard.tripped(now=2.0) is True
    guard.reset()
    assert guard.tripped(now=2.0) is False


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_max_restarts(bad):
    with pytest.raises(ValueError):
        RestartLoopGuard(max_restarts=bad)


@pytest.mark.parametrize("bad", [0, -5.0])
def test_invalid_window_seconds(bad):
    with pytest.raises(ValueError):
        RestartLoopGuard(window_seconds=bad)
