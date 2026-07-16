"""
Unit tests for LoopGuard no-progress detection.

Regression coverage for issue #3073: async / long-running tool workflows that
poll a changing status (e.g. IN_PROGRESS -> COMPLETE) must NOT be halted by the
"no progress" heuristic, while a genuinely stuck loop (identical results) still
halts.
"""

from praisonaiagents.escalation.loop_guard import (
    LoopGuard,
    LoopGuardConfig,
    GuardAction,
)


def _run_to_halt(guard, tool_name, results):
    """Record each result then check; return the first HALT decision or None."""
    for i, res in enumerate(results):
        guard.record(tool_name, {"i": i}, True, result=res)
        decision = guard.check(tool_name, {"i": i}, is_pre_execution=False)
        if decision.action == GuardAction.HALT:
            return decision
    return None


def test_async_polling_with_changing_results_not_halted():
    """Distinct polling results across many calls should not trigger a halt."""
    guard = LoopGuard(LoopGuardConfig())
    guard.reset_turn()

    results = [f"IN_PROGRESS elapsed={n}s" for n in range(10)] + ["COMPLETE"]
    decision = _run_to_halt(guard, "check_transform_status", results)

    assert decision is None


def test_no_progress_streak_resets_on_changing_result():
    """A run of identical results followed by a distinct result resets the streak.

    This mirrors an async poll that stays IN_PROGRESS for several calls and then
    changes, which must not be halted by the no-progress heuristic.
    """
    guard = LoopGuard(LoopGuardConfig())
    guard.reset_turn()

    # 5 identical polls (below no_progress_halt=8) then distinct results that
    # reset the streak. Kept under the per-tool idempotent halt threshold (12)
    # so only the no-progress heuristic is exercised.
    results = ["IN_PROGRESS"] * 5 + ["COMPLETE"] + [f"page {n}" for n in range(4)]
    decision = _run_to_halt(guard, "check_status", results)

    assert decision is None


def test_identical_results_still_halt():
    """A genuinely stuck loop (identical results) must still halt."""
    guard = LoopGuard(LoopGuardConfig())
    guard.reset_turn()

    results = ["IN_PROGRESS"] * 12
    decision = _run_to_halt(guard, "check_status", results)

    assert decision is not None
    assert decision.code == "no_progress_halt"


def test_disabled_guard_never_halts():
    """A disabled guard allows everything."""
    guard = LoopGuard(LoopGuardConfig(enabled=False))
    guard.reset_turn()

    decision = _run_to_halt(guard, "check_status", ["SAME"] * 20)

    assert decision is None


def test_falsy_results_still_halt():
    """Repeated falsy outputs (e.g. empty search results) must still halt.

    The upstream detector drops the fingerprint for falsy results, so the guard
    wraps them; otherwise a tool repeatedly returning ``[]`` / ``""`` would
    silently bypass no-progress detection.
    """
    for falsy in ("", [], {}, 0, False):
        guard = LoopGuard(LoopGuardConfig())
        guard.reset_turn()

        results = [falsy] * 12
        decision = _run_to_halt(guard, "search_files", results)

        assert decision is not None, f"falsy result {falsy!r} bypassed the guard"
        assert decision.code == "no_progress_halt"


def test_distinct_tools_same_value_not_halted():
    """Different tools returning a common value must not share one stuck streak."""
    guard = LoopGuard(LoopGuardConfig())
    guard.reset_turn()

    # 10 distinct tools each returning "ok" — changing tool == progress.
    decision = None
    for n in range(10):
        tool = f"tool_{n}"
        guard.record(tool, {"n": n}, True, result="ok")
        d = guard.check(tool, {"n": n}, is_pre_execution=False)
        if d.action == GuardAction.HALT:
            decision = d
            break

    assert decision is None


def test_mark_progress_resets_streak():
    """An explicit progress marker resets the no-progress streak."""
    guard = LoopGuard(LoopGuardConfig())
    guard.reset_turn()

    # 5 identical polls, then mark progress, then 5 more — neither run reaches
    # the halt threshold of 8 once the marker resets the boundary.
    decision = None
    for i in range(5):
        guard.record("check_status", {"i": i}, True, result="IN_PROGRESS")
        d = guard.check("check_status", {"i": i}, is_pre_execution=False)
        if d.action == GuardAction.HALT:
            decision = d
    guard.mark_progress("step-done")
    for i in range(5, 10):
        guard.record("check_status", {"i": i}, True, result="IN_PROGRESS")
        d = guard.check("check_status", {"i": i}, is_pre_execution=False)
        if d.action == GuardAction.HALT:
            decision = d

    assert decision is None
