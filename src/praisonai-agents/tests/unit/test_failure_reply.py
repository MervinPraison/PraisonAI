"""Tests for the visible failure-outcome primitive (render_failure_reply)."""

from praisonaiagents.bots import FailureReply, render_failure_reply
from praisonaiagents.bots.failure import (
    REASON_AUTH_EXPIRED,
    REASON_AUTH_PERMANENT,
    REASON_MISSING_KEY,
    REASON_RATE_LIMIT,
    REASON_TIMEOUT,
    REASON_BUDGET_EXHAUSTED,
    REASON_DOOM_LOOP,
    REASON_NEEDS_HELP,
    REASON_CANCELLED,
    REASON_UNKNOWN,
)
from praisonaiagents.errors import (
    LLMError,
    PraisonAIConfigError,
    BudgetExceededError,
)
from praisonaiagents.run_outcome import AgentRunOutcome, TerminationReason


def test_expired_auth_error_maps_to_reauth_copy():
    err = LLMError("401 Unauthorized", error_category="auth")
    reply = render_failure_reply(err)
    assert isinstance(reply, FailureReply)
    assert reply.reason_code == REASON_AUTH_EXPIRED
    assert "praisonai onboard" in reply.text
    assert reply.retryable is False


def test_permanent_auth_error_maps_to_permanent_copy():
    err = LLMError("403 Forbidden", error_category="auth_permanent")
    reply = render_failure_reply(err)
    assert reply.reason_code == REASON_AUTH_PERMANENT
    assert reply.retryable is False


def test_missing_key_config_error_prefers_remediation_hint():
    err = PraisonAIConfigError("OpenAI key not set", config_key="OPENAI_API_KEY")
    reply = render_failure_reply(err)
    assert reply.reason_code == REASON_MISSING_KEY
    # The concrete remediation_hint is surfaced verbatim.
    assert "OPENAI_API_KEY" in reply.text
    assert reply.retryable is False


def test_rate_limit_error_is_retryable():
    err = LLMError("429 Too Many Requests", error_category="rate_limit")
    reply = render_failure_reply(err)
    assert reply.reason_code == REASON_RATE_LIMIT
    assert reply.retryable is True
    assert "wait" in reply.text.lower()


def test_budget_error_maps_to_budget_copy():
    err = BudgetExceededError("agent", 1.0, 0.5)
    reply = render_failure_reply(err)
    assert reply.reason_code == REASON_BUDGET_EXHAUSTED
    assert reply.retryable is False


def test_outcome_timeout_status():
    outcome = AgentRunOutcome.timeout("timed out after 30s")
    reply = render_failure_reply(outcome)
    assert reply.reason_code == REASON_TIMEOUT
    assert reply.retryable is True


def test_outcome_cancelled_status():
    outcome = AgentRunOutcome.cancelled()
    reply = render_failure_reply(outcome)
    assert reply.reason_code == REASON_CANCELLED


def test_outcome_termination_reason_doom_loop():
    outcome = AgentRunOutcome.failure(
        "halted",
        context={"termination_reason": TerminationReason.DOOM_LOOP},
    )
    reply = render_failure_reply(outcome)
    assert reply.reason_code == REASON_DOOM_LOOP


def test_outcome_termination_reason_budget():
    outcome = AgentRunOutcome.failure(
        "halted",
        context={"termination_reason": TerminationReason.BUDGET_EXHAUSTED.value},
    )
    reply = render_failure_reply(outcome)
    assert reply.reason_code == REASON_BUDGET_EXHAUSTED


def test_outcome_termination_reason_needs_help():
    outcome = AgentRunOutcome.failure(
        "need more info",
        context={"termination_reason": TerminationReason.NEEDS_HELP},
    )
    reply = render_failure_reply(outcome)
    assert reply.reason_code == REASON_NEEDS_HELP


def test_unknown_input_degrades_to_visible_generic_reply():
    reply = render_failure_reply("some raw string")
    assert reply.reason_code == REASON_UNKNOWN
    assert reply.text  # always visible, never blank
    assert reply.retryable is False


def test_reply_is_frozen():
    reply = render_failure_reply(LLMError("x", error_category="unknown"))
    try:
        reply.text = "mutated"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("FailureReply should be immutable (frozen)")
