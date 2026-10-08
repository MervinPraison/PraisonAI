"""Regression tests: parallel/loop fan-out delivers the EXACT upstream output.

Issue #5716: ``Parallel`` (and parallel ``Loop``) silently replaced
``previous_output`` with a lossy head+tail excerpt for every branch whenever the
upstream step produced more than ~3,000 chars -- dropping the middle with no
opt-out and no default-level warning. The fix makes exact pass-through the
default (``context="full"``) and keeps the token-saving excerpt as an explicit
opt-in (``context="truncate"``/``"summarize"``) that now warns when it drops
data.

These tests pin that contract so a later change cannot quietly return to silent
data loss:

* default delivers the exact bytes (middle marker survives) for Parallel,
  parallel Loop, and a multi-step parallel Loop;
* ``context="truncate"`` opts back into the excerpt and warns;
* invalid ``context`` values are rejected at construction;
* YAML has parity -- ``context: truncate`` reaches the pattern object.
"""

import logging

import pytest

from praisonaiagents import Workflow, WorkflowContext, StepResult
from praisonaiagents.task.task import Task
from praisonaiagents.workflows import parallel, loop
from praisonaiagents.workflows.workflows import Parallel, Loop


# A payload large enough to trip the old >3000 char / >1000 token excerpt, with
# a unique marker buried in the middle so a head+tail truncation provably drops
# it. The marker is what distinguishes exact pass-through from the excerpt.
MIDDLE_MARKER = "SECRET-MIDDLE-MARKER-7f3a"
_HALF = "x " * 3000  # ~6000 chars each side; marker sits in the exact middle
BIG = _HALF + MIDDLE_MARKER + _HALF


def _upstream(payload):
    return lambda ctx: StepResult(output=payload)


def _capture(sink):
    """Branch/iteration handler that records the exact context it received."""
    def run(ctx: WorkflowContext) -> StepResult:
        sink.append(ctx.previous_result)
        return StepResult(output="ok")
    return run


# ---------------------------------------------------------------------------
# Default (context="full"): exact pass-through, no data loss
# ---------------------------------------------------------------------------

def test_parallel_default_delivers_exact_upstream_output():
    seen = []
    wf = Workflow(steps=[
        Task(name="producer", handler=_upstream(BIG), max_retries=0),
        parallel([
            Task(name="a", handler=_capture(seen), max_retries=0),
            Task(name="b", handler=_capture(seen), max_retries=0),
        ]),
    ])
    assert wf.start("go")["status"] == "completed"

    assert len(seen) == 2
    for received in seen:
        assert received == BIG, "default Parallel must hand over the exact bytes"
        assert MIDDLE_MARKER in received, "the middle was dropped under the default"


def test_parallel_loop_default_delivers_exact_upstream_output():
    seen = []
    wf = Workflow(steps=[
        Task(name="producer", handler=_upstream(BIG), max_retries=0),
        loop(step=Task(name="iter", handler=_capture(seen), max_retries=0),
             over="items", parallel=True),
    ], variables={"items": ["one", "two"]})
    assert wf.start("go")["status"] == "completed"

    assert len(seen) == 2
    for received in seen:
        assert received == BIG, "default parallel Loop must hand over the exact bytes"
        assert MIDDLE_MARKER in received


def test_parallel_multi_step_loop_default_delivers_exact_upstream_output():
    seen = []
    wf = Workflow(steps=[
        Task(name="producer", handler=_upstream(BIG), max_retries=0),
        loop(steps=[Task(name="iter", handler=_capture(seen), max_retries=0)],
             over="items", parallel=True),
    ], variables={"items": ["one", "two"]})
    assert wf.start("go")["status"] == "completed"

    assert len(seen) == 2
    for received in seen:
        assert received == BIG
        assert MIDDLE_MARKER in received


# ---------------------------------------------------------------------------
# Opt-in reduction (context="truncate"/"summarize"): excerpt + warn
# ---------------------------------------------------------------------------

def test_parallel_truncate_opts_back_into_the_excerpt_and_warns(caplog):
    seen = []
    wf = Workflow(steps=[
        Task(name="producer", handler=_upstream(BIG), max_retries=0),
        parallel([
            Task(name="a", handler=_capture(seen), max_retries=0),
            Task(name="b", handler=_capture(seen), max_retries=0),
        ], context="truncate"),
    ])
    with caplog.at_level(logging.WARNING):
        assert wf.start("go")["status"] == "completed"

    for received in seen:
        assert received != BIG, "truncate must excerpt the upstream output"
        assert MIDDLE_MARKER not in received, "truncate drops the middle"
        assert len(received) < len(BIG)
    assert any("Parallel context='truncate'" in rec.getMessage() for rec in caplog.records), (
        f"dropping data must warn: {[r.getMessage() for r in caplog.records]}"
    )


def test_parallel_loop_truncate_opts_back_into_the_excerpt_and_warns(caplog):
    seen = []
    wf = Workflow(steps=[
        Task(name="producer", handler=_upstream(BIG), max_retries=0),
        loop(step=Task(name="iter", handler=_capture(seen), max_retries=0),
             over="items", parallel=True, context="truncate"),
    ], variables={"items": ["one", "two"]})
    with caplog.at_level(logging.WARNING):
        assert wf.start("go")["status"] == "completed"

    for received in seen:
        assert received != BIG
        assert MIDDLE_MARKER not in received
    assert any("Loop context='truncate'" in rec.getMessage() for rec in caplog.records), (
        f"dropping data must warn: {[r.getMessage() for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_parallel_rejects_invalid_context():
    with pytest.raises(ValueError, match="context"):
        Parallel(steps=[], context="nonsense")


def test_loop_rejects_invalid_context():
    sentinel = Task(name="x", handler=_upstream("ok"), max_retries=0)
    with pytest.raises(ValueError, match="context"):
        Loop(step=sentinel, context="summarize")  # Loop has no summarize mode


def test_defaults_are_full():
    sentinel = Task(name="x", handler=_upstream("ok"), max_retries=0)
    assert Parallel(steps=[]).context == "full"
    assert Loop(step=sentinel).context == "full"


# ---------------------------------------------------------------------------
# YAML parity: context must reach the pattern object
# ---------------------------------------------------------------------------

def test_yaml_parallel_forwards_context():
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    parser = YAMLWorkflowParser()
    pattern = parser._parse_parallel_step({"parallel": [], "context": "truncate"})
    assert pattern.context == "truncate"
    # Default stays lossless when unspecified.
    assert parser._parse_parallel_step({"parallel": []}).context == "full"


def test_yaml_loop_forwards_context():
    from praisonaiagents.workflows.yaml_parser import YAMLWorkflowParser

    parser = YAMLWorkflowParser()
    parser._agents = {"proc": object()}
    pattern = parser._parse_loop_step(
        {"loop": {"over": "items", "parallel": True, "context": "truncate", "step": "proc"}}
    )
    assert pattern.context == "truncate"
    default = parser._parse_loop_step(
        {"loop": {"over": "items", "parallel": True, "step": "proc"}}
    )
    assert default.context == "full"
