"""
Regression tests for DoomLoopDetector._check_no_progress window boundary.

The no-progress heuristic only counts progress markers recorded within the
current window. A marker recorded *during* the window's oldest action is
timestamped before that action's record_action() timestamp (which is set at
completion), so filtering on the oldest action's timestamp would wrongly drop
it and report NO_PROGRESS despite genuine recent progress.
"""

import time

from praisonaiagents.escalation.doom_loop import (
    DoomLoopConfig,
    DoomLoopDetector,
)


def _make_detector(steps: int = 3) -> DoomLoopDetector:
    return DoomLoopDetector(DoomLoopConfig(max_no_progress_steps=steps))


def test_marker_during_window_first_action_still_counts():
    """Progress made during the window's oldest action must suppress NO_PROGRESS."""
    det = _make_detector(steps=3)

    # Marker recorded *before* the first windowed action completes.
    det.mark_progress("did-real-work")
    time.sleep(0.001)
    for i in range(3):
        det.record_action("poll", {"i": i}, f"same-{0}", True)

    assert det._check_no_progress() is False


def test_marker_before_window_is_ignored():
    """A stale marker predating the window must not suppress NO_PROGRESS."""
    det = _make_detector(steps=3)

    # One early action + marker, then a full window of identical results with
    # no further progress. The early marker is outside the window and must be
    # ignored so the stuck window is detected.
    det.mark_progress("early-success")
    det.record_action("setup", {"i": -1}, "start", True)
    time.sleep(0.001)
    for i in range(3):
        det.record_action("poll", {"i": i}, "stuck", True)

    assert det._check_no_progress() is True


def test_recent_marker_within_window_suppresses():
    """A marker recorded mid-window still suppresses NO_PROGRESS."""
    det = _make_detector(steps=3)

    det.record_action("poll", {"i": 0}, "stuck", True)
    det.mark_progress("mid-window-progress")
    det.record_action("poll", {"i": 1}, "stuck", True)
    det.record_action("poll", {"i": 2}, "stuck", True)

    assert det._check_no_progress() is False
