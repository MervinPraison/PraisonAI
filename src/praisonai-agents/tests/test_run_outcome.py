"""Tests for the canonical RunOutcome terminal-outcome contract."""

import asyncio

from praisonaiagents.agent.run_outcome import RunOutcome
from praisonaiagents.agent.execution_mixin import ExecutionMixin


def test_completed_factory():
    o = RunOutcome.completed("hi")
    assert o.reason == "completed"
    assert o.output == "hi"
    assert o.error is None
    assert o.succeeded is True


def test_from_exception_timeout_is_not_hard_timeout():
    # A bare asyncio.TimeoutError is a nested-operation timeout at this
    # boundary. Only the run-level budget (enforced by _astart_with_outcome)
    # owns hard_timeout, so this must NOT be promoted to hard_timeout.
    assert RunOutcome.from_exception(asyncio.TimeoutError()).reason == "failed"


def test_from_exception_cancelled():
    assert RunOutcome.from_exception(asyncio.CancelledError()).reason == "cancelled"


def test_from_exception_name_matching():
    class SupersededError(Exception):
        pass

    class DrainAbort(Exception):
        pass

    assert RunOutcome.from_exception(SupersededError()).reason == "cancelled"
    assert RunOutcome.from_exception(DrainAbort()).reason == "aborted"


def test_from_exception_failed_is_redacted_string():
    o = RunOutcome.from_exception(ValueError("boom"))
    assert o.reason == "failed"
    assert o.error == "boom"
    assert o.succeeded is False


def test_outcome_is_frozen():
    o = RunOutcome.completed("x")
    try:
        o.reason = "failed"  # type: ignore[misc]
    except Exception as exc:  # dataclasses.FrozenInstanceError
        assert "Frozen" in type(exc).__name__
    else:
        raise AssertionError("RunOutcome should be immutable")


class _FakeAgent(ExecutionMixin):
    planning = False
    backend = None
    autonomy_enabled = False
    stream = None

    def __init__(self, behavior):
        self.behavior = behavior

    def _load_history_context(self):
        pass

    def _auto_save_session(self):
        pass

    def chat(self, prompt, **kwargs):
        if self.behavior == "ok":
            return "answer"
        raise ValueError("kaboom")

    async def achat(self, prompt, **kwargs):
        if self.behavior == "ok":
            return "async-answer"
        if self.behavior == "slow":
            await asyncio.sleep(5)
            return "too-late"
        if self.behavior == "nested_timeout":
            # A nested operation exhausted its OWN budget while the run budget
            # (if any) remained; surfaces as a bare asyncio.TimeoutError.
            raise asyncio.TimeoutError()
        if self.behavior == "block":
            await asyncio.sleep(3600)
            return "never"
        raise ValueError("async-kaboom")


def test_run_returns_string_by_default():
    assert _FakeAgent("ok").run("hi") == "answer"


def test_run_returns_outcome_on_completion():
    o = _FakeAgent("ok").run("hi", return_outcome=True)
    assert o.reason == "completed" and o.output == "answer"


def test_run_returns_outcome_on_failure_without_raising():
    o = _FakeAgent("bad").run("hi", return_outcome=True)
    assert o.reason == "failed" and o.error == "kaboom"


def test_astart_outcome_completed():
    o = asyncio.run(_FakeAgent("ok").astart("hi", return_outcome=True))
    assert o.reason == "completed" and o.output == "async-answer"


def test_astart_outcome_hard_timeout():
    o = asyncio.run(_FakeAgent("slow").astart("hi", return_outcome=True, timeout=0.05))
    assert o.reason == "hard_timeout"


def test_astart_outcome_failed():
    o = asyncio.run(_FakeAgent("bad").astart("hi", return_outcome=True))
    assert o.reason == "failed" and o.error == "async-kaboom"


def test_astart_nested_timeout_is_failed_with_budget():
    # With a generous run budget, a nested operation TimeoutError must NOT be
    # promoted to a run-budget hard_timeout — it is a plain failure.
    o = asyncio.run(
        _FakeAgent("nested_timeout").astart(
            "hi", return_outcome=True, timeout=5
        )
    )
    assert o.reason == "failed"


def test_astart_external_cancellation_propagates():
    # Cancelling the enclosing task must raise CancelledError (host shutdown
    # semantics), not be swallowed into a benign RunOutcome.
    async def scenario():
        task = asyncio.ensure_future(
            _FakeAgent("block").astart("hi", return_outcome=True, timeout=30)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    try:
        asyncio.run(scenario())
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("external cancellation should propagate")
