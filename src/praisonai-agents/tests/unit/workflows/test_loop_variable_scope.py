"""
Regression tests: variables written *inside* a ``loop()`` body must survive it.

Sibling of the ``Parallel`` data-loss fix (#4932). Every step inside a loop wrote
its ``output_variable`` into a ``copy.deepcopy(all_variables)`` that was thrown
away at the end of each iteration, in both the sequential and the parallel path,
so the result was silently discarded while the run still reported "completed":

    parallel   inner='I'   control='AFTER'
    repeat     inner='I'   control='AFTER'
    if_        inner='I'   control='AFTER'
    route      inner='I'   control='AFTER'
    loop       inner=None  control='AFTER'   <- only loop lost it

Every test below carries a ``control`` assertion (a step *outside* the loop whose
``output_variable`` has always worked) so none of them can pass vacuously if
variable recording breaks wholesale.

THE RULE these tests pin
------------------------
1. A sequential loop is its body unrolled, so it runs against the shared scope
   like Repeat/If/Route: no isolation, iteration N sees iteration N-1's writes.
2. A parallel loop must isolate (concurrent writes to one dict is a data race),
   so it merges each iteration's *delta* back in **item order**, never completion
   order.
3. Both therefore end with the **last item's** value for a variable the body
   rewrites each iteration - what the unrolled sequence would produce. Unlike
   ``Parallel`` this is not warned about: N iterations writing one
   ``output_variable`` N times is the normal shape of a loop, not an accident.
4. The loop's own control variables (``item``/``var_name``, ``loop_index``,
   ``item.<key>``) are loop machinery, not results, and stay loop-scoped in both
   modes.
5. Sequential and parallel must agree on all of the above - pinned directly by
   ``test_sequential_and_parallel_loops_agree_on_final_variables`` so neither can
   later be "fixed" into a race or back into silent loss.
"""

import logging

import pytest

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.task.task import Task
from praisonaiagents.workflows import loop, parallel

MODES = [False, True]
MODE_IDS = ["sequential", "parallel"]


def _after(record=None):
    def run(ctx: WorkflowContext) -> StepResult:
        if record is not None:
            record.append(dict(ctx.variables))
        return StepResult(output="AFTER")
    return Task(name="after", handler=run, output_variable="control", max_retries=0)


def _echo_item(name="inner", output_variable="inner_var"):
    return Task(
        name=name,
        handler=lambda ctx: StepResult(output=f"X-{ctx.variables.get('item')}"),
        output_variable=output_variable,
        max_retries=0,
    )


# ---------------------------------------------------------------------------
# The reproduction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_loop_body_output_variable_survives_the_loop(is_parallel):
    """The bug: ``inner_var`` was absent from every later step and the result."""
    seen = []
    wf = Workflow(
        steps=[
            loop(steps=[_echo_item()], over="items", parallel=is_parallel,
                 output_variable="collected"),
            _after(record=seen),
        ],
        variables={"items": ["a", "b"]},
    )
    result = wf.start("go")
    variables = result["variables"]

    assert result["status"] == "completed"
    assert variables.get("inner_var") == "X-b", (
        f"the loop body's output_variable was discarded: {sorted(variables)}"
    )
    # Control: a step outside the loop has always worked, so this proves the test
    # measures the loop-specific loss and not a broken harness.
    assert variables.get("control") == "AFTER"

    # And it must be visible to the *next* step, not merely in the result dict.
    assert seen and seen[0].get("inner_var") == "X-b"

    # The loop's own aggregate is untouched by the fix.
    assert variables["collected"] == ["X-a", "X-b"]
    assert variables["loop_outputs"] == ["X-a", "X-b"]


@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_default_output_variable_name_of_a_loop_body_step_also_survives(is_parallel):
    """A body step with no explicit output_variable writes ``{name}_output``."""
    wf = Workflow(
        steps=[
            loop(steps=[Task(name="alpha",
                             handler=lambda ctx: StepResult(output=f"A-{ctx.variables.get('item')}"),
                             max_retries=0)],
                 over="items", parallel=is_parallel),
            _after(),
        ],
        variables={"items": ["a", "b"]},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("alpha_output") == "A-b"
    assert variables.get("control") == "AFTER"  # control


@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_every_iterations_distinct_writes_survive(is_parallel):
    """Each iteration writes its *own* key; none of them may be dropped.

    Kills a merge that keeps only one iteration's delta (the first or the last).
    """
    def writer(ctx: WorkflowContext) -> StepResult:
        idx = ctx.variables.get("loop_index")
        return StepResult(output=f"o{idx}", variables={f"seen_{idx}": ctx.variables.get("item")})

    wf = Workflow(
        steps=[
            loop(steps=[Task(name="w", handler=writer, max_retries=0)],
                 over="items", parallel=is_parallel),
            _after(),
        ],
        variables={"items": ["a", "b", "c"]},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("seen_0") == "a", "the first iteration's writes were dropped"
    assert variables.get("seen_1") == "b"
    assert variables.get("seen_2") == "c", "the last iteration's writes were dropped"
    assert variables.get("control") == "AFTER"  # control


@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_last_item_wins_a_reused_output_variable(is_parallel):
    """Iterations share one step name, so the *last item* wins - not the first.

    Kills a merge applied in reverse item order, and (for the parallel loop) one
    applied in completion order.
    """
    wf = Workflow(
        steps=[
            loop(steps=[_echo_item()], over="items", parallel=is_parallel),
            _after(),
        ],
        variables={"items": ["first", "middle", "last"]},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("inner_var") == "X-last", (
        "a reused output_variable must end on the last item's value"
    )
    assert variables.get("control") == "AFTER"  # control


def test_parallel_loop_winner_does_not_depend_on_completion_order():
    """The first item's iteration finishes last here; item order still wins."""
    import time

    def slow_first(ctx: WorkflowContext) -> StepResult:
        if ctx.variables.get("loop_index") == 0:
            time.sleep(0.25)
        return StepResult(output=f"X-{ctx.variables.get('item')}")

    wf = Workflow(
        steps=[
            loop(steps=[Task(name="inner", handler=slow_first,
                             output_variable="inner_var", max_retries=0)],
                 over="items", parallel=True, max_workers=4),
            _after(),
        ],
        variables={"items": ["first", "last"]},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("inner_var") == "X-last"
    assert variables.get("control") == "AFTER"  # control


def test_a_reused_output_variable_across_iterations_is_not_warned_about(caplog):
    """Unlike Parallel branches, cross-iteration collision is normal, not a bug."""
    wf = Workflow(
        steps=[loop(steps=[_echo_item()], over="items", parallel=True), _after()],
        variables={"items": ["a", "b", "c"]},
    )
    with caplog.at_level(logging.WARNING):
        variables = wf.start("go")["variables"]

    assert variables.get("inner_var") == "X-c"
    assert variables.get("control") == "AFTER"  # control
    assert not any("inner_var" in rec.getMessage() for rec in caplog.records), (
        "a loop must not warn once per item about its own body's output_variable: "
        f"{[r.getMessage() for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Sequential / parallel parity - the gate that stops either drifting
# ---------------------------------------------------------------------------

def _run_both_modes():
    def writer(ctx: WorkflowContext) -> StepResult:
        idx = ctx.variables.get("loop_index")
        return StepResult(
            output=f"X-{ctx.variables.get('item')}",
            variables={f"per_{idx}": ctx.variables.get("item")},
        )

    def build(is_parallel):
        return Workflow(
            steps=[
                loop(steps=[
                        Task(name="one", handler=writer, output_variable="shared", max_retries=0),
                        Task(name="two",
                             handler=lambda ctx: StepResult(output=f"2-{ctx.variables.get('shared')}"),
                             output_variable="second", max_retries=0),
                     ],
                     over="items", parallel=is_parallel, output_variable="collected"),
                _after(),
            ],
            variables={"items": ["a", "b", "c"], "untouched": "U"},
        )

    return (
        build(False).start("go")["variables"],
        build(True).start("go")["variables"],
    )


def test_sequential_and_parallel_loops_agree_on_final_variables():
    """The two modes must end with the same scope.

    Parallel is meant to be a faster way to run the same loop, not a different
    semantics. This is the gate: any change that makes one mode propagate the
    body's writes differently from the other fails here by name.
    """
    seq, par = _run_both_modes()

    interesting = ["shared", "second", "per_0", "per_1", "per_2",
                   "collected", "loop_outputs", "untouched", "control"]
    seq_view = {k: seq.get(k) for k in interesting}
    par_view = {k: par.get(k) for k in interesting}

    assert seq_view == par_view, (
        f"sequential and parallel loops disagree:\n  seq={seq_view}\n  par={par_view}"
    )
    # Not vacuous: the values really are the loop body's writes, last item winning.
    assert seq_view["shared"] == "X-c"
    assert seq_view["second"] == "2-X-c"
    assert seq_view["per_0"] == "a" and seq_view["per_2"] == "c"
    assert seq_view["control"] == "AFTER"  # control


# ---------------------------------------------------------------------------
# Loop control variables stay loop-scoped (both modes)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_loop_control_variables_do_not_leak_out(is_parallel):
    """``item``/``loop_index``/``item.<key>`` are machinery, not results."""
    wf = Workflow(
        steps=[
            loop(steps=[Task(name="inner",
                             handler=lambda ctx: StepResult(output=str(ctx.variables.get("item.k"))),
                             output_variable="inner_var", max_retries=0)],
                 over="items", parallel=is_parallel),
            _after(),
        ],
        variables={"items": [{"k": "a"}, {"k": "b"}]},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("inner_var") == "b"  # the loop body's write did escape
    assert "item" not in variables
    assert "loop_index" not in variables
    assert "item.k" not in variables
    assert variables.get("control") == "AFTER"  # control


@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_a_pre_existing_variable_named_item_is_restored_after_the_loop(is_parallel):
    """A loop must not clobber a workflow variable that shares its var_name."""
    wf = Workflow(
        steps=[
            loop(steps=[_echo_item()], over="items", parallel=is_parallel),
            _after(),
        ],
        variables={"items": ["a", "b"], "item": "ORIGINAL"},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("item") == "ORIGINAL"
    assert variables.get("inner_var") == "X-b"
    assert variables.get("control") == "AFTER"  # control


@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_untouched_variables_keep_the_parents_own_object(is_parallel):
    """A loop body works on copies (parallel); only real writes may merge back."""
    original = {"a": [1, 2, 3]}
    wf = Workflow(
        steps=[
            loop(steps=[_echo_item()], over="items", parallel=is_parallel),
            _after(),
        ],
        variables={"items": ["a", "b"], "payload": original},
    )
    variables = wf.start("go")["variables"]

    assert variables["payload"] is original, (
        "an untouched variable was replaced by a loop iteration's deep copy"
    )
    assert variables.get("inner_var") == "X-b"
    assert variables.get("control") == "AFTER"  # control


# ---------------------------------------------------------------------------
# Nesting: a loop inside a Parallel branch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_loop_nested_in_a_parallel_branch_propagates_body_writes_only(is_parallel):
    """The branch merge must carry the loop body's writes but not ``item``.

    The sequential loop now runs against the scope it is given - which, inside a
    Parallel branch, is that branch's write-tracking copy. Its control variables
    must not be recorded as branch writes and leak into the workflow.
    """
    wf = Workflow(
        steps=[
            parallel([
                loop(steps=[_echo_item()], over="items", parallel=is_parallel),
                Task(name="sibling", handler=lambda ctx: StepResult(output="S"),
                     output_variable="sibling_var", max_retries=0),
            ]),
            _after(),
        ],
        variables={"items": ["a", "b"]},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("inner_var") == "X-b", (
        "a loop body's write was lost on the way out of a Parallel branch"
    )
    assert variables.get("sibling_var") == "S"  # control: sibling branch merged
    assert "item" not in variables
    assert "loop_index" not in variables
    assert variables.get("control") == "AFTER"  # control


# ---------------------------------------------------------------------------
# The sequential loop is its body unrolled
# ---------------------------------------------------------------------------

def test_sequential_iterations_see_the_previous_iterations_writes():
    """No concurrency means no isolation: a sequential loop can accumulate.

    (The parallel loop cannot offer this - its iterations run concurrently - so
    this is deliberately not parametrized over both modes.)
    """
    def accumulate(ctx: WorkflowContext) -> StepResult:
        so_far = ctx.variables.get("acc") or ""
        return StepResult(output=so_far + str(ctx.variables.get("item")),
                          variables={"acc": so_far + str(ctx.variables.get("item"))})

    wf = Workflow(
        steps=[
            loop(steps=[Task(name="acc_step", handler=accumulate, max_retries=0)],
                 over="items", parallel=False),
            _after(),
        ],
        variables={"items": ["a", "b", "c"]},
    )
    variables = wf.start("go")["variables"]

    assert variables.get("acc") == "abc"
    assert variables["loop_outputs"] == ["a", "ab", "abc"]
    assert variables.get("control") == "AFTER"  # control


@pytest.mark.parametrize("is_parallel", MODES, ids=MODE_IDS)
def test_a_body_step_writing_the_control_name_still_does_not_leak_it(is_parallel):
    """Even a deliberate ``output_variable="item"`` stays loop-scoped.

    Without this the two modes would disagree: the sequential loop restores the
    name unconditionally, so the parallel loop must strip it from its delta even
    though a body step really did write it.
    """
    wf = Workflow(
        steps=[
            loop(steps=[Task(name="inner",
                             handler=lambda ctx: StepResult(output=f"X-{ctx.variables.get('item')}"),
                             output_variable="item", max_retries=0)],
                 over="items", parallel=is_parallel),
            _after(),
        ],
        variables={"items": ["a", "b"]},
    )
    variables = wf.start("go")["variables"]

    assert "item" not in variables, (
        "the loop's control variable escaped the loop"
    )
    assert variables["loop_outputs"] == ["X-a", "X-b"]  # control: the body did run
    assert variables.get("control") == "AFTER"  # control
