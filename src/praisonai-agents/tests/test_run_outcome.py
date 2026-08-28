"""Tests for the canonical RunOutcome terminal-outcome contract."""

import asyncio

from praisonaiagents.agent.run_outcome import (
    RunOutcome,
    classify_finish_reason,
    PROVIDER_BLOCK_REASONS,
)
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

    def __init__(self, behavior, stop_reason="completed"):
        self.behavior = behavior
        self.last_stop_reason = stop_reason

    def _load_history_context(self):
        pass

    def _auto_save_session(self):
        pass

    def chat(self, prompt, **kwargs):
        if self.behavior == "ok":
            return "answer"
        if self.behavior == "empty":
            return ""
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


# --- Provider finish_reason classification (content-filter/refusal/length) ---


def test_classify_finish_reason_normal_stops_are_none():
    assert classify_finish_reason(None) is None
    assert classify_finish_reason("stop") is None
    assert classify_finish_reason("tool_calls") is None
    assert classify_finish_reason("function_call") is None
    # Unknown/absent finish reasons behave exactly as today.
    assert classify_finish_reason("some_new_reason") is None


def test_classify_finish_reason_blocks():
    assert classify_finish_reason("content_filter") == "content_filtered"
    assert classify_finish_reason("CONTENT_FILTER") == "content_filtered"
    assert classify_finish_reason("length") == "length_truncated"
    assert classify_finish_reason("max_tokens") == "length_truncated"
    # A safety refusal is carried independently of finish_reason.
    assert classify_finish_reason("stop", refusal="I can't help with that") == "refused"


def test_provider_block_reasons_outrank_failed_but_not_cancel():
    from praisonaiagents.agent.run_outcome import _REASON_PRECEDENCE
    for reason in PROVIDER_BLOCK_REASONS:
        assert _REASON_PRECEDENCE[reason] > _REASON_PRECEDENCE["failed"]
        assert _REASON_PRECEDENCE[reason] < _REASON_PRECEDENCE["cancelled"]
        assert _REASON_PRECEDENCE[reason] < _REASON_PRECEDENCE["hard_timeout"]


def test_run_outcome_surfaces_provider_block_over_empty_completed():
    # An empty result from a content-filtered turn must surface the specific,
    # actionable reason instead of a silent empty "completed".
    o = _FakeAgent("empty", stop_reason="content_filtered").run(
        "hi", return_outcome=True
    )
    assert o.reason == "content_filtered"
    assert o.succeeded is False


def test_run_outcome_completed_when_no_block():
    o = _FakeAgent("ok", stop_reason="completed").run("hi", return_outcome=True)
    assert o.reason == "completed" and o.output == "answer"


def test_astart_outcome_surfaces_refusal():
    o = asyncio.run(
        _FakeAgent("ok", stop_reason="refused").astart("hi", return_outcome=True)
    )
    assert o.reason == "refused"
    assert o.succeeded is False


def test_agent_last_stop_reason_prefers_own_block_over_stale_backend():
    # Regression: an agent-owned provider block (OpenAI-native classification)
    # must win over a stale backend reason like "max_steps"; otherwise the
    # actionable "refused" is masked and _outcome_for_result reports success.
    from praisonaiagents.agent.agent import Agent

    agent = Agent(instructions="test", llm="gpt-4o-mini")
    agent._last_stop_reason = "refused"

    class _StaleBackend:
        _last_stop_reason = "max_steps"

    agent.llm_instance = _StaleBackend()
    assert agent.last_stop_reason == "refused"


def test_agent_last_stop_reason_backend_used_when_own_completed():
    # When the agent recorded nothing specific, the backend reason still wins.
    from praisonaiagents.agent.agent import Agent

    agent = Agent(instructions="test", llm="gpt-4o-mini")
    agent._last_stop_reason = "completed"

    class _Backend:
        _last_stop_reason = "max_steps"

    agent.llm_instance = _Backend()
    assert agent.last_stop_reason == "max_steps"
