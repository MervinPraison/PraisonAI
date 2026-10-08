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
# Loop: the same data loss, fixed separately - see test_loop_variable_scope.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("is_parallel", [False, True])
def test_loop_body_variables_survive_and_the_two_modes_agree(is_parallel):
    """Loop had the identical defect and it is fixed the same way.

    This test previously asserted the opposite - that ``inner_var`` was
    deliberately iteration-scoped - on the reasoning that N iterations share one
    step name so the Loop's ``loop_outputs`` aggregate is the right answer. That
    reasoning did not survive contact with the rest of the package:

    * ``Repeat`` has exactly the same property (N iterations, one step name) and
      has always run against the shared scope with the last iteration winning;
    * ``loop_outputs`` only holds each iteration's *last* step's output, so an
      earlier step's ``output_variable`` in a multi-step body - and any
      ``StepResult.variables`` write - was lost with no aggregate to recover it
      from, silently, while the run reported "completed".

    Loop is now the unrolled sequence it looks like: the body's writes escape,
    last item wins, and the loop's own control variables stay loop-scoped. The
    full rule and its mutation gates live in ``test_loop_variable_scope.py``.
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
    assert variables.get("inner_var") == "X-b"
    assert "item" not in variables and "loop_index" not in variables
    assert variables.get("after_output") == "AFTER"  # control


# ---------------------------------------------------------------------------
# Write detection is by identity, not value equality
# ---------------------------------------------------------------------------

def test_equal_valued_write_still_wins_collision_in_declaration_order(caplog):
    """A later branch writing the same value the variable already held is a write.

    Baseline ``shared="SAME"``; the first branch rebinds it to ``"OTHER"`` and the
    second rebinds it back to ``"SAME"``. Sequential execution of these steps ends
    with ``"SAME"`` (second is last), so the parallel merge must too. Value-equality
    detection dropped the second branch's write because it equalled the baseline,
    leaving ``"OTHER"`` and suppressing the collision warning.
    """
    wf = Workflow(steps=[
        parallel([
            Task(name="first", handler=_handler("OTHER"),
                 output_variable="shared", max_retries=0),
            Task(name="second", handler=_handler("SAME"),
                 output_variable="shared", max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"shared": "SAME"})
    with caplog.at_level(logging.WARNING):
        variables = wf.start("go")["variables"]

    assert variables.get("shared") == "SAME", (
        "an equal-valued write was dropped, breaking declaration-order semantics"
    )
    assert variables.get("after_output") == "AFTER"  # control
    assert any("shared" in rec.getMessage() and "Parallel branches" in rec.getMessage()
               for rec in caplog.records), (
        "an equal-valued collision must still be reported"
    )


# ---------------------------------------------------------------------------
# Non-deep-copyable workflow variables (#5715)
# ---------------------------------------------------------------------------

class _Uncopyable:
    """A value whose ``__deepcopy__`` raises, standing in for a lock/client."""

    def __deepcopy__(self, memo):
        raise TypeError("cannot pickle _Uncopyable")


@pytest.mark.parametrize("is_parallel", [False, True])
def test_uncopyable_variable_does_not_crash_parallel_or_loop(is_parallel):
    """An un-copyable scope variable no branch reads must not abort the run.

    Before the fix, ``_execute_parallel`` / the parallel ``Loop`` seed did an
    unconditional ``copy.deepcopy(all_variables)`` which raised ``TypeError`` on
    the un-copyable value, killing the whole workflow even though no branch
    touched it.
    """
    wf = Workflow(steps=[
        loop(steps=[Task(name="inner",
                         handler=lambda ctx: StepResult(output=f"X-{ctx.variables.get('item')}"),
                         output_variable="inner_var", max_retries=0)],
             over="items", parallel=is_parallel, output_variable="collected"),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"items": ["a", "b"], "client": _Uncopyable()})
    variables = wf.start("go")["variables"]

    assert variables["collected"] == ["X-a", "X-b"]
    assert variables.get("after_output") == "AFTER"  # control


def test_parallel_block_tolerates_uncopyable_variable():
    """Same guarantee for a plain ``Parallel`` block, not just a loop."""
    wf = Workflow(steps=[
        parallel([
            Task(name="a", handler=_handler("A"), output_variable="va", max_retries=0),
            Task(name="b", handler=_handler("B"), output_variable="vb", max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"client": _Uncopyable()})
    variables = wf.start("go")["variables"]

    assert variables["va"] == "A" and variables["vb"] == "B"
    assert variables.get("after_output") == "AFTER"  # control


def test_uncopyable_leaf_is_shared_but_surrounding_container_is_isolated():
    """A nested mutable sibling of an un-copyable leaf must stay branch-local.

    ``state = {'client': <uncopyable>, 'rows': []}`` cannot be deep-copied as a
    whole, but the fallback must still copy the surrounding dict and its ``rows``
    list so one branch appending to ``rows`` is invisible to its sibling. Only
    the un-copyable ``client`` leaf is shared by reference.
    """
    client = _Uncopyable()

    def append_row(label):
        def run(ctx: WorkflowContext) -> StepResult:
            ctx.variables["state"]["rows"].append(label)
            return StepResult(output=label,
                              variables={f"rows_{label}": list(ctx.variables["state"]["rows"])})
        return run

    wf = Workflow(steps=[
        parallel([
            Task(name="a", handler=append_row("A"), max_retries=0),
            Task(name="b", handler=append_row("B"), max_retries=0),
        ], max_workers=2),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"state": {"client": client, "rows": []}})
    variables = wf.start("go")["variables"]

    # Each branch saw only its own append, never the sibling's.
    assert variables["rows_A"] == ["A"], variables["rows_A"]
    assert variables["rows_B"] == ["B"], variables["rows_B"]
    # The un-copyable client object is shared by reference, not cloned.
    assert variables["state"]["client"] is client
    assert variables.get("after_output") == "AFTER"  # control


def test_cross_variable_aliasing_is_preserved_within_a_branch():
    """Two scope variables that alias one object stay aliased inside a branch.

    The old whole-scope ``copy.deepcopy`` used a single memo, so
    ``records`` and ``state['records']`` pointing at the same list remained one
    list after copying. Per-value copying would split them; the shared memo keeps
    them connected, so a write through one name is seen through the other.
    """
    shared_list = [1, 2, 3]

    def mutate_and_report(ctx: WorkflowContext) -> StepResult:
        ctx.variables["records"].append(4)
        return StepResult(
            output="ok",
            variables={"alias_sees_write": ctx.variables["state"]["records"][-1]},
        )

    wf = Workflow(steps=[
        parallel([
            Task(name="mutator", handler=mutate_and_report, max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"records": shared_list, "state": {"records": shared_list}})
    variables = wf.start("go")["variables"]

    assert variables["alias_sees_write"] == 4, (
        "cross-variable aliasing was broken: the branch's copies of 'records' and "
        "'state.records' were separate objects"
    )
    # Parent's original object is untouched (branch worked on its own copy).
    assert shared_list == [1, 2, 3]
    assert variables.get("after_output") == "AFTER"  # control


def test_deeply_nested_seed_data_survives_an_uncopyable_leaf():
    """Nested seed around an un-copyable leaf must not vanish in a branch.

    A failed ``copy.deepcopy`` leaves *unfinished* copies in its memo. The
    fallback must discard them and rebuild node-by-node; reusing them dropped the
    nested data so ``{'outer': {'mid': {'client': lock, 'rows': [...]}}}`` reached
    a branch as ``{'outer': {}}`` (two-levels-deep regression, #5717 review).
    """
    client = _Uncopyable()

    def report(ctx: WorkflowContext) -> StepResult:
        state = ctx.variables["state"]
        return StepResult(
            output="ok",
            variables={
                "mid_keys": sorted(state["outer"]["mid"].keys()),
                "rows_seen": list(state["outer"]["mid"]["rows"]),
                "sibling_seen": list(state["outer"]["sibling"]),
            },
        )

    wf = Workflow(steps=[
        parallel([Task(name="r", handler=report, max_retries=0)]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"state": {"outer": {
        "mid": {"client": client, "rows": [1, 2, 3]},
        "sibling": [9, 9],
    }}})
    variables = wf.start("go")["variables"]

    assert variables["mid_keys"] == ["client", "rows"], variables["mid_keys"]
    assert variables["rows_seen"] == [1, 2, 3]
    assert variables["sibling_seen"] == [9, 9]
    assert variables.get("after_output") == "AFTER"  # control


def test_uncopyable_fallback_preserves_container_subclass_behaviour():
    """namedtuple / defaultdict seeds keep their type when a sibling is un-copyable.

    The old fallback flattened container subclasses: a ``namedtuple`` became a
    plain ``tuple`` (named-field access raised ``AttributeError``) and a
    ``defaultdict`` lost its factory. The branch must see the original behaviour.
    """
    import collections

    Point = collections.namedtuple("Point", ["x", "client"])
    client = _Uncopyable()
    point = Point(1, client)

    seed_dd = collections.defaultdict(list)
    seed_dd["client"] = client
    seed_dd["rows"].append(1)

    def report(ctx: WorkflowContext) -> StepResult:
        p = ctx.variables["point"]
        dd = ctx.variables["bag"]
        dd["autovivified"].append("ok")  # factory must still fire inside the branch
        return StepResult(output="ok", variables={
            "named_field": p.x,                       # AttributeError if flattened
            "is_namedtuple": hasattr(p, "_fields"),
            "dd_type_ok": isinstance(dd, collections.defaultdict),
            "dd_autoviv": list(dd["autovivified"]),
        })

    wf = Workflow(steps=[
        parallel([Task(name="r", handler=report, max_retries=0)]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"point": point, "bag": seed_dd})
    variables = wf.start("go")["variables"]

    assert variables["named_field"] == 1
    assert variables["is_namedtuple"] is True
    assert variables["dd_type_ok"] is True
    assert variables["dd_autoviv"] == ["ok"]
    assert variables.get("after_output") == "AFTER"  # control


def test_required_arg_container_subclass_with_uncopyable_leaf_does_not_crash():
    """A list/set subclass whose constructor needs args must not abort the run.

    The fallback rebuilt containers via ``value.__class__()``; a subclass whose
    ``__init__`` requires arguments raised *inside* the fallback, aborting the
    ``Parallel`` block before any branch ran - the very crash class this PR fixes
    (#5717 merge-gate P1). The ``dict`` branch already guarded this; ``list`` and
    ``set`` must too. On constructor failure the fallback degrades to a plain
    ``list``/``set`` (still isolated) rather than raising.
    """
    client = _Uncopyable()

    class _RequiredArgList(list):
        def __init__(self, required):  # no zero-arg form
            super().__init__()
            self.required = required

    class _RequiredArgSet(set):
        def __init__(self, required):  # no zero-arg form
            super().__init__()
            self.required = required

    # The un-copyable client sits *inside* each subclass, so ``copy.deepcopy``
    # raises and the node-by-node fallback runs - which is where the unguarded
    # ``value.__class__()`` constructor would have raised.
    bad_list = _RequiredArgList("x")
    bad_list.extend([client, 1, 2])
    bad_set = _RequiredArgSet("y")
    bad_set.update({client, 1, 2})

    def report(ctx: WorkflowContext) -> StepResult:
        return StepResult(output="ok", variables={
            "list_vals": sorted(v for v in ctx.variables["bad_list"] if v is not client),
            "list_has_client": any(v is client for v in ctx.variables["bad_list"]),
            "set_vals": sorted(v for v in ctx.variables["bad_set"] if v is not client),
            "set_has_client": any(v is client for v in ctx.variables["bad_set"]),
        })

    wf = Workflow(steps=[
        parallel([Task(name="r", handler=report, max_retries=0)]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"bad_list": bad_list, "bad_set": bad_set})
    variables = wf.start("go")["variables"]

    assert variables["list_vals"] == [1, 2]
    assert variables["list_has_client"] is True  # un-copyable leaf shared by ref
    assert variables["set_vals"] == [1, 2]
    assert variables["set_has_client"] is True
    assert variables.get("after_output") == "AFTER"  # control


def test_untouched_value_with_non_bool_inequality_is_not_a_write(caplog):
    """A carried-through object whose ``!=`` is not a bool must not become a write.

    ``_NonBoolEq.__ne__`` returns a non-bool (like a numpy array), so value-based
    detection ``bool(value != original)`` raised and conservatively classified the
    untouched value as written - replacing the parent's object with a branch-local
    clone and emitting a spurious collision warning across branches. Identity
    detection never evaluates ``!=`` for an untouched key.
    """
    class _NonBoolEq:
        def __ne__(self, other):
            return [True]  # not a bool; bool([True]) is True but the array case raises
        __hash__ = None

    sentinel = _NonBoolEq()
    wf = Workflow(steps=[
        parallel([
            Task(name="one", handler=_handler("1"), output_variable="v1", max_retries=0),
            Task(name="two", handler=_handler("2"), output_variable="v2", max_retries=0),
        ]),
        Task(name="after", handler=_handler("AFTER"), max_retries=0),
    ], variables={"carried": sentinel})
    with caplog.at_level(logging.WARNING):
        variables = wf.start("go")["variables"]

    assert variables["v1"] == "1" and variables["v2"] == "2"
    assert variables["carried"] is sentinel, (
        "an untouched non-comparable value was replaced by a branch's deep copy"
    )
    assert not any("carried" in rec.getMessage() for rec in caplog.records), (
        "an untouched value must not produce a collision warning"
    )
