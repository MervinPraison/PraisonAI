"""
Regression tests: variables written inside a ``Parallel`` block must survive.

Every step inside a ``Parallel`` used to write its ``output_variable`` into a
``copy.deepcopy(all_variables)`` that was thrown away when the branch returned,
so the result was silently discarded:

    branch_a_output present  False
    branch_b_output present  False
    after_output   (control)  True

The isolation itself is deliberate (concurrent branches writing one shared dict
is a data race); what was missing was the merge back. These tests pin the merge
rule: declaration-order application, last-declared branch wins a key collision
(with a warning), only real writes merged, and partial_ok keeping the writes a
failed branch had already made.
"""

import logging
import time

import pytest

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.task.task import Task
from praisonaiagents.workflows import parallel, loop


def _handler(output, record=None, sleep=0.0):
    def run(ctx: WorkflowContext) -> StepResult:
        if sleep:
            time.sleep(sleep)
        if record is not None:
            record.append(dict(ctx.variables))
        return StepResult(output=output)
    return run


# ---------------------------------------------------------------------------
# The reproduction
# ---------------------------------------------------------------------------

def test_parallel_branch_output_variables_survive_the_block():
    """Both branches' output_variable writes must be visible after the block.

    The ``after_output`` control assertion keeps this test from passing
    vacuously: it fails on the buggy code too if variables stop being recorded
    at all.
    """
    seen = []
    wf = Workflow(steps=[
        parallel([
            Task(name="branch_a", handler=_handler("A"),
                 output_variable="branch_a_output", max_retries=0),
            Task(name="branch_b", handler=_handler("B"),
                 output_variable="branch_b_output", max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER", record=seen),
             output_variable="after_output", max_retries=0),
    ])
    result = wf.start("go")
    variables = result["variables"]

    assert result["status"] == "completed"
    assert variables.get("branch_a_output") == "A", (
        f"branch_a's output_variable was discarded: {sorted(variables)}"
    )
    assert variables.get("branch_b_output") == "B", (
        f"branch_b's output_variable was discarded: {sorted(variables)}"
    )
    # Control: a step outside the block has always worked, so this asserts the
    # test is measuring the parallel-specific loss and not a broken harness.
    assert variables.get("after_output") == "AFTER"

    # And the branch variables must be visible to the *next* step, not merely
    # in the final result dict.
    assert seen and seen[0].get("branch_a_output") == "A"
    assert seen[0].get("branch_b_output") == "B"


def test_default_step_output_variable_name_also_survives():
    """A branch step with no explicit output_variable writes ``{name}_output``."""
    wf = Workflow(steps=[
        parallel([
            Task(name="alpha", handler=_handler("A"), max_retries=0),
            Task(name="beta", handler=_handler("B"), max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ])
    variables = wf.start("go")["variables"]

    assert variables.get("alpha_output") == "A"
    assert variables.get("beta_output") == "B"
    assert variables.get("after_output") == "AFTER"  # control


# ---------------------------------------------------------------------------
# The merge rule
# ---------------------------------------------------------------------------

def test_key_collision_last_declared_branch_wins_and_warns(caplog):
    """Two branches writing the same variable is ambiguous, not silent.

    The winner is the last branch in *declaration* order - what sequential
    execution of the same steps would produce - and the collision is logged.
    """
    wf = Workflow(steps=[
        parallel([
            Task(name="first", handler=_handler("FROM-FIRST"),
                 output_variable="shared", max_retries=0),
            Task(name="second", handler=_handler("FROM-SECOND"),
                 output_variable="shared", max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ])
    with caplog.at_level(logging.WARNING):
        variables = wf.start("go")["variables"]

    assert variables.get("shared") == "FROM-SECOND"
    assert variables.get("after_output") == "AFTER"  # control
    assert any("shared" in rec.getMessage() and "Parallel branches" in rec.getMessage()
               for rec in caplog.records), (
        f"collision was not reported: {[r.getMessage() for r in caplog.records]}"
    )


def test_collision_winner_does_not_depend_on_completion_order():
    """The first-declared branch finishes last here; declaration order still wins."""
    wf = Workflow(steps=[
        parallel([
            Task(name="slow", handler=_handler("FROM-SLOW", sleep=0.25),
                 output_variable="shared", max_retries=0),
            Task(name="fast", handler=_handler("FROM-FAST"),
                 output_variable="shared", max_retries=0),
        ], max_workers=2),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ])
    variables = wf.start("go")["variables"]

    assert variables.get("shared") == "FROM-FAST"
    assert variables.get("after_output") == "AFTER"  # control


def test_branches_do_not_write_back_variables_they_never_touched():
    """Only real writes merge; an untouched value keeps the parent's own object.

    Each branch works on a deep copy, so merging a branch's whole dict back
    would replace shared inputs with per-branch clones.
    """
    original = {"a": [1, 2, 3]}
    wf = Workflow(steps=[
        parallel([
            Task(name="one", handler=_handler("1"), output_variable="v1", max_retries=0),
            Task(name="two", handler=_handler("2"), output_variable="v2", max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"payload": original})
    variables = wf.start("go")["variables"]

    assert variables["v1"] == "1" and variables["v2"] == "2"
    assert variables["payload"] is original, (
        "an untouched variable was replaced by a branch's deep copy"
    )


def test_a_branch_may_deliberately_overwrite_an_existing_variable():
    """output_variable naming a pre-existing workflow variable must take effect."""
    wf = Workflow(steps=[
        parallel([
            Task(name="rewriter", handler=_handler("NEW"),
                 output_variable="topic", max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"topic": "OLD"})
    variables = wf.start("go")["variables"]

    assert variables["topic"] == "NEW"
    assert variables.get("after_output") == "AFTER"  # control


def test_partial_ok_keeps_the_variables_a_failed_branch_did_write():
    """"partial_ok" means partial results are kept - including partial variables.

    The failing branch here writes a variable through ``StepResult.variables``
    and is then rejected by its guardrail, so it is a branch that genuinely
    failed yet genuinely wrote something. Its own ``output_variable`` is never
    reached (the failure path returns before that write), so nothing the failure
    invented can leak in.
    """
    def writes_then_fails_guardrail(ctx: WorkflowContext) -> StepResult:
        return StepResult(output="OK", variables={"partial_var": "OK"})

    wf = Workflow(steps=[
        parallel([
            Task(name="half_done", handler=writes_then_fails_guardrail,
                 guardrails=lambda result: (False, "never valid"),
                 output_variable="half_done_var", max_retries=0,
                 on_error="continue"),
            Task(name="healthy", handler=_handler("H"),
                 output_variable="healthy_var", max_retries=0),
        ], on_failure="partial_ok"),
    ])
    result = wf.start("go")
    variables = result["variables"]

    assert result["status"] == "failed"  # the branch really did fail
    assert variables.get("healthy_var") == "H"  # control: good branch merged
    assert variables.get("partial_var") == "OK", (
        "partial_ok discarded a variable the failed branch had already written"
    )
    assert "half_done_var" not in variables, (
        "a failed step's output_variable must not be written"
    )


@pytest.mark.parametrize("mode", ["fail_fast", "fail_all"])
def test_failing_modes_still_raise_and_merge_nothing(mode):
    """fail_fast/fail_all abort the block; the merge must not paper over that."""
    from praisonaiagents.workflows.workflows import WorkflowStepError

    def boom(ctx: WorkflowContext) -> StepResult:
        raise RuntimeError("boom")

    seen = []
    wf = Workflow(steps=[
        parallel([
            Task(name="bad", handler=boom, output_variable="bad_var", max_retries=0),
        ], on_failure=mode),
        Task(name="after", handler=_handler("AFTER", record=seen), max_retries=0),
    ])
    with pytest.raises(WorkflowStepError):
        wf.start("go")

    # Nothing downstream ran, so no branch variable can have leaked forward.
    assert seen == []


# ---------------------------------------------------------------------------
# Loop: deliberately iteration-scoped, and identical parallel vs sequential
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_parallel", [False, True])
def test_loop_iteration_variables_stay_iteration_scoped(is_parallel):
    """Loop is NOT the same case as Parallel and must not be "fixed" to match.

    N iterations share one step name, so a per-iteration output_variable has N
    conflicting values; the aggregate is exposed through the Loop's own
    ``output_variable`` / ``loop_outputs`` instead. Sequential and parallel
    loops behave identically, and that parity is what this test pins.
    """
    wf = Workflow(steps=[
        loop(steps=[Task(name="inner",
                         handler=lambda ctx: StepResult(output=f"X-{ctx.variables.get('item')}"),
                         output_variable="inner_var", max_retries=0)],
             over="items", parallel=is_parallel, output_variable="collected"),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"items": ["a", "b"]})
    variables = wf.start("go")["variables"]

    assert variables["collected"] == ["X-a", "X-b"]
    assert variables["loop_outputs"] == ["X-a", "X-b"]
    assert "inner_var" not in variables
    assert variables.get("after_output") == "AFTER"  # control
