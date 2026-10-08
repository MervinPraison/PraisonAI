"""
Regression tests for issue #5714 — Parallel(on_failure="fail_fast") must fail
fast, Parallel(timeout=...) must bound wall-clock time, and an abandoned branch
must not corrupt a later run's status.

These use handler Tasks (no LLM) with threading.Event gates so the ordering is
deterministic: a *blocked* first-declared branch and a *fast-failing* later
branch prove that failure is observed in completion order (not submission order)
and that shutdown no longer waits for the slow sibling. Every blocked worker is
released in a finally so no thread leaks past the test.
"""

import threading
import time

import pytest

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.task.task import Task
from praisonaiagents.workflows import Parallel, parallel
from praisonaiagents.workflows.workflows import WorkflowStepError


def test_fail_fast_raises_before_slow_sibling_finishes():
    """A later-declared branch that fails quickly must fail the run promptly,
    without blocking on an earlier-declared branch that is still running."""
    release = threading.Event()
    slow_finished = threading.Event()

    def slow(ctx: WorkflowContext) -> StepResult:
        # Branch 0: blocks until released. fail_fast must NOT wait for it.
        release.wait(timeout=10)
        slow_finished.set()
        return StepResult(output="slow-done")

    def quick_fail(ctx: WorkflowContext) -> StepResult:
        raise RuntimeError("boom")

    steps = [
        Task(name="slow", handler=slow, max_retries=0),
        Task(name="quick_fail", handler=quick_fail, max_retries=0),
    ]
    wf = Workflow(steps=[parallel(steps, max_workers=2, on_failure="fail_fast")])

    try:
        start = time.monotonic()
        with pytest.raises(WorkflowStepError):
            wf.start("go")
        elapsed = time.monotonic() - start

        assert wf.status == "failed"
        # Raised well before the 10s slow branch could finish on its own.
        assert elapsed < 5, f"fail_fast blocked on the slow sibling ({elapsed:.1f}s)"
        assert not slow_finished.is_set(), (
            "fail_fast waited for the abandoned slow branch to complete"
        )
    finally:
        release.set()


def test_timeout_raises_instead_of_hanging():
    """Parallel(timeout=...) must raise once the wall-clock bound elapses rather
    than hang on a branch that never returns."""
    release = threading.Event()

    def hangs(ctx: WorkflowContext) -> StepResult:
        release.wait(timeout=10)
        return StepResult(output="done")

    steps = [Task(name="hangs", handler=hangs, max_retries=0)]
    wf = Workflow(steps=[parallel(steps, max_workers=1, timeout=1)])

    try:
        start = time.monotonic()
        with pytest.raises(WorkflowStepError):
            wf.start("go")
        elapsed = time.monotonic() - start

        assert wf.status == "failed"
        assert elapsed < 5, f"timeout did not bound the hung branch ({elapsed:.1f}s)"
    finally:
        release.set()


def test_non_positive_timeout_is_rejected():
    """timeout=0 (and negatives) are truthiness-false and would silently disable
    the bound — reject them at construction instead of hanging forever."""
    with pytest.raises(ValueError):
        Parallel(steps=[], timeout=0)
    with pytest.raises(ValueError):
        Parallel(steps=[], timeout=-1)
    with pytest.raises(ValueError):
        parallel([], timeout=0)
    # None (no bound) and a positive value remain valid.
    assert Parallel(steps=[], timeout=None).timeout is None
    assert Parallel(steps=[], timeout=2).timeout == 2


def test_abandoned_branch_cannot_fail_a_later_run():
    """A fail_fast branch abandoned by run #1 must not write "failed" onto run #2
    when it finally fails after run #2 has already begun."""
    release = threading.Event()

    def quick_fail(ctx: WorkflowContext) -> StepResult:
        raise RuntimeError("run1-boom")

    def slow_then_fail(ctx: WorkflowContext) -> StepResult:
        # Abandoned by run #1's fail_fast; fails only after we release it, which
        # the test does *after* run #2 has completed successfully.
        release.wait(timeout=10)
        raise RuntimeError("late-boom")

    run1_steps = [
        Task(name="slow_then_fail", handler=slow_then_fail, max_retries=0),
        Task(name="quick_fail", handler=quick_fail, max_retries=0),
    ]
    wf = Workflow(steps=[parallel(run1_steps, max_workers=2, on_failure="fail_fast")])

    try:
        # Run #1: fails fast on the quick branch, abandoning the slow one.
        with pytest.raises(WorkflowStepError):
            wf.start("go")
        assert wf.status == "failed"

        # Run #2 on the SAME instance: a trivially successful pipeline.
        def ok(ctx: WorkflowContext) -> StepResult:
            return StepResult(output="ok")

        wf.steps = [Task(name="ok", handler=ok, max_retries=0)]
        result2 = wf.start("go")
        assert result2["status"] == "completed"

        # Now let the abandoned run #1 branch fail. It must NOT flip the
        # instance status that run #2 already set to completed.
        release.set()
        time.sleep(0.3)
        assert wf.status == "completed", (
            "an abandoned branch from a previous run corrupted a later run's status"
        )
    finally:
        release.set()
