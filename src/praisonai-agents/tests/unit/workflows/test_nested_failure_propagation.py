"""
Regression tests for issue #4190.

Every nested workflow pattern (loop/parallel/when/route/repeat) used to route a
failing step through ``_apply_step_policies``, which folded ``f"Error: {e}"`` into
the step's *output* and never consulted ``on_error``. The result was that wrapping
a working pipeline in any pattern silently lost failure detection: the run reported
``status="completed"`` and the next step consumed the exception text as if it were
real data.

These tests assert the fixed behaviour:
  * a failing step fails the run in every pattern, and
  * the exception text is never handed forward as the next step's input.
"""

import pytest

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.task.task import Task
from praisonaiagents.workflows import loop, when, parallel, repeat, route


def _four_steps_with_a_raise_in_step_two():
    """Build four handler steps where step 2 raises RuntimeError('boom').

    ``calls`` records ``(step_name, prompt)`` for each executed step so a test can
    assert that no downstream step was ever handed the exception text as input.
    ``max_retries=0`` keeps the failing step from sleeping through retry backoff.
    """
    calls = []

    def s1(ctx: WorkflowContext) -> StepResult:
        calls.append(("s1", str(ctx.previous_result)))
        return StepResult(output="s1-out")

    def s2(ctx: WorkflowContext) -> StepResult:
        calls.append(("s2", str(ctx.previous_result)))
        raise RuntimeError("boom")

    def s3(ctx: WorkflowContext) -> StepResult:
        calls.append(("s3", str(ctx.previous_result)))
        return StepResult(output="s3-out")

    def s4(ctx: WorkflowContext) -> StepResult:
        calls.append(("s4", str(ctx.previous_result)))
        return StepResult(output="s4-out")

    steps = [
        Task(name="s1", handler=s1, max_retries=0),
        Task(name="s2", handler=s2, max_retries=0),
        Task(name="s3", handler=s3, max_retries=0),
        Task(name="s4", handler=s4, max_retries=0),
    ]
    return steps, calls


def _wrap(kind, steps):
    if kind == "none":
        return Workflow(steps=steps)
    if kind == "loop":
        return Workflow(steps=[loop(steps=steps, over="items")],
                        variables={"items": ["only"]})
    if kind == "when":
        return Workflow(steps=[when("{{go}} == 1", then_steps=steps)],
                        variables={"go": 1})
    if kind == "parallel":
        # A single-branch parallel keeps the four steps sequential inside the
        # branch, so the failure ordering is deterministic.
        return Workflow(steps=[parallel([loop(steps=steps, over="items")])],
                        variables={"items": ["only"]})
    if kind == "repeat":
        return Workflow(steps=[repeat(loop(steps=steps, over="items"),
                                      max_iterations=1)],
                        variables={"items": ["only"]})
    if kind == "route":
        return Workflow(steps=[route({"go": steps}, default=steps)])
    raise ValueError(kind)


@pytest.mark.parametrize("wrap", ["none", "loop", "when", "parallel", "repeat", "route"])
def test_a_failing_step_fails_the_run_in_every_pattern(wrap):
    """A pipeline that reports failure at the top level must not report success
    merely because it was wrapped — and the next step must not receive the
    exception text as its input."""
    steps, calls = _four_steps_with_a_raise_in_step_two()
    result = _wrap(wrap, steps).start("go")

    assert result["status"] == "failed", (
        f"pattern '{wrap}' reported {result['status']!r} for a run containing a "
        f"failed step"
    )
    assert not any("boom" in prompt for _, prompt in calls), (
        f"pattern '{wrap}' handed the exception text forward as input: {calls}"
    )


def test_top_level_control_still_fails():
    """Sanity check: the un-wrapped pipeline already failed on main."""
    steps, _ = _four_steps_with_a_raise_in_step_two()
    assert Workflow(steps=steps).start("go")["status"] == "failed"


def test_on_error_continue_reports_failed_but_keeps_going():
    """on_error='continue' is a legitimate mode: the loop may survive one bad
    item, but the run status must still reflect the failure and the error must
    not be handed to the next step as input."""
    calls = []

    def ok(ctx: WorkflowContext) -> StepResult:
        calls.append(("ok", str(ctx.previous_result)))
        return StepResult(output="ok-out")

    def boom(ctx: WorkflowContext) -> StepResult:
        calls.append(("boom", str(ctx.previous_result)))
        raise RuntimeError("kaboom")

    steps = [
        Task(name="ok", handler=ok, max_retries=0),
        Task(name="boom", handler=boom, max_retries=0, on_error="continue"),
        Task(name="ok2", handler=ok, max_retries=0),
    ]
    result = Workflow(steps=[loop(steps=steps, over="items")],
                      variables={"items": ["only"]}).start("go")

    assert result["status"] == "failed"
    assert not any("kaboom" in prompt for _, prompt in calls)


@pytest.mark.parametrize("wrap", ["loop", "when", "repeat", "route"])
def test_nested_stop_halts_the_outer_workflow(wrap):
    """A nested step with the default on_error='stop' must terminate the whole
    workflow, not merely its own pattern iteration: a following top-level step
    must never run."""
    calls = []

    def boom(ctx: WorkflowContext) -> StepResult:
        calls.append("boom")
        raise RuntimeError("boom")

    def after(ctx: WorkflowContext) -> StepResult:
        calls.append("after")
        return StepResult(output="after-out")

    inner = [Task(name="boom", handler=boom, max_retries=0)]
    if wrap == "loop":
        pattern = loop(steps=inner, over="items")
    elif wrap == "when":
        pattern = when("{{go}} == 1", then_steps=inner)
    elif wrap == "repeat":
        pattern = repeat(loop(steps=inner, over="items"), max_iterations=1)
    else:
        pattern = route({"go": inner}, default=inner)

    after_step = Task(name="after", handler=after, max_retries=0)
    result = Workflow(steps=[pattern, after_step],
                      variables={"items": ["only"], "go": 1}).start("go")

    assert result["status"] == "failed"
    assert "after" not in calls, (
        f"pattern '{wrap}' ran a later top-level step despite on_error='stop'"
    )


def test_parallel_fail_fast_does_not_mask_failure_with_typeerror():
    """A nested step surfaces its error as a string; the parallel fail_fast path
    must not `raise ... from <str>` (which would itself raise TypeError). The run
    must simply report failed."""
    def boom(ctx: WorkflowContext) -> StepResult:
        raise RuntimeError("boom")

    inner = [Task(name="boom", handler=boom, max_retries=0)]
    wf = Workflow(steps=[parallel([loop(steps=inner, over="items")],
                                  on_failure="fail_fast")],
                  variables={"items": ["only"]})
    result = wf.start("go")

    assert result["status"] == "failed"
