"""
Visible failure-outcome primitive for bot gateways.

:func:`classify_final` (``bots/silence.py``) guarantees a visible outcome for a
*blank* turn, but says nothing about a turn that **failed** (expired auth,
missing key, rate limit, timeout, budget/doom-loop) — where the user today sees
a generic ``Error: <msg>`` or a silent downgrade. A rich error taxonomy already
exists in :mod:`praisonaiagents.errors` and :mod:`praisonaiagents.run_outcome`,
but nothing maps it to a *user-facing, actionable* reply, so every channel
adapter re-decides it ad hoc (the drift this closes).

This module is the failure-path counterpart of ``classify_final`` /
``resolve_ingress_admission``: a single, pure, dependency-free decision that maps
an :class:`~praisonaiagents.run_outcome.AgentRunOutcome` or a
:class:`~praisonaiagents.errors.PraisonAIError` to a typed :class:`FailureReply`
with next-step copy keyed by failure class, reusing the existing
``remediation_hint``. Every adapter renders ``reply.text`` and records
``reply.reason_code`` instead of hand-rolling ``Error: …`` strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cost/cycles
    from ..errors import PraisonAIError
    from ..run_outcome import AgentRunOutcome


# Machine-readable failure reason codes. Module constants (like the ``REASON_*``
# codes in ``admission.py``) so callers record/compare without re-typing string
# literals — exactly the drift that produced the per-adapter ``Error: …`` copy.
REASON_AUTH_EXPIRED = "auth_expired"
REASON_AUTH_PERMANENT = "auth_permanent"
REASON_MISSING_KEY = "missing_key"
REASON_RATE_LIMIT = "rate_limit"
REASON_OVERLOADED = "overloaded"
REASON_TIMEOUT = "timeout"
REASON_BUDGET_EXHAUSTED = "budget_exhausted"
REASON_DOOM_LOOP = "doom_loop"
REASON_NEEDS_HELP = "needs_help"
REASON_CANCELLED = "cancelled"
REASON_CONTEXT_OVERFLOW = "context_overflow"
REASON_MODEL_NOT_FOUND = "model_not_found"
REASON_FORMAT_ERROR = "format_error"
REASON_UNKNOWN = "unknown"


# Static, user-facing next-step copy keyed by failure class. Kept deterministic
# and channel-agnostic so the same guidance appears on every transport. A
# concrete ``remediation_hint`` (e.g. from ``PraisonAIConfigError``) always wins
# over these defaults when present.
_REASON_TEXT = {
    REASON_AUTH_EXPIRED: (
        "I couldn't complete that - the model credential has expired. "
        "Run `praisonai onboard` to re-authenticate, then resend."
    ),
    REASON_AUTH_PERMANENT: (
        "I couldn't complete that - the model credential was rejected. "
        "Check the API key/permissions, then run `praisonai onboard` and resend."
    ),
    REASON_MISSING_KEY: (
        "I couldn't complete that - a required credential is missing. "
        "Run `praisonai onboard` (or `praisonai doctor`) to set it up, then resend."
    ),
    REASON_RATE_LIMIT: (
        "I couldn't complete that - the provider is rate-limiting requests. "
        "Please wait a moment and resend."
    ),
    REASON_OVERLOADED: (
        "I couldn't complete that - the provider is temporarily overloaded. "
        "Please wait a moment and resend."
    ),
    REASON_TIMEOUT: (
        "I couldn't complete that in time - the request timed out. "
        "Please resend, or try a shorter request."
    ),
    REASON_BUDGET_EXHAUSTED: (
        "I stopped before finishing - this turn hit its budget limit. "
        "Raise the budget or narrow the task, then resend."
    ),
    REASON_DOOM_LOOP: (
        "I stopped before finishing - I detected a repeating loop and halted to "
        "avoid wasting effort. Try rephrasing the request, then resend."
    ),
    REASON_NEEDS_HELP: (
        "I need a bit more to continue - please clarify or provide the missing "
        "detail, then resend."
    ),
    REASON_CANCELLED: "That request was cancelled before it finished.",
    REASON_CONTEXT_OVERFLOW: (
        "I couldn't complete that - the conversation is too long for the model. "
        "Start a fresh thread or shorten the request, then resend."
    ),
    REASON_MODEL_NOT_FOUND: (
        "I couldn't complete that - the configured model is unavailable. "
        "Check the model name in your config, then resend."
    ),
    REASON_FORMAT_ERROR: (
        "I couldn't complete that - the request or configuration was invalid. "
        "Please check the input and resend."
    ),
    REASON_UNKNOWN: "I couldn't complete that due to an unexpected error. Please resend.",
}

# Which failure classes are worth retrying without user intervention. Mirrors the
# taxonomy in ``errors.AgentErrorKind`` / ``AgentRunOutcome.is_retryable`` so the
# adapter can decide whether to offer a "retry" affordance.
_RETRYABLE_REASONS = frozenset(
    {REASON_RATE_LIMIT, REASON_OVERLOADED, REASON_TIMEOUT}
)

# Map the closed ``AgentErrorKind`` taxonomy to a user-facing reason code. Auth
# is split into expired vs permanent so re-authentication guidance is precise.
_ERROR_KIND_TO_REASON = {
    "auth": REASON_AUTH_EXPIRED,
    "auth_permanent": REASON_AUTH_PERMANENT,
    "rate_limit": REASON_RATE_LIMIT,
    "overloaded": REASON_OVERLOADED,
    "context_overflow": REASON_CONTEXT_OVERFLOW,
    "idle_timeout": REASON_TIMEOUT,
    "billing": REASON_BUDGET_EXHAUSTED,
    "model_not_found": REASON_MODEL_NOT_FOUND,
    "format_error": REASON_FORMAT_ERROR,
    "validation": REASON_FORMAT_ERROR,
    "unknown": REASON_UNKNOWN,
}

# Map an ``AgentRunOutcome`` termination context / status to a reason code.
_TERMINATION_TO_REASON = {
    "budget_exhausted": REASON_BUDGET_EXHAUSTED,
    "doom_loop": REASON_DOOM_LOOP,
    "needs_help": REASON_NEEDS_HELP,
    "timeout": REASON_TIMEOUT,
    "cancelled": REASON_CANCELLED,
    "interrupted": REASON_CANCELLED,
}


@dataclass(frozen=True)
class FailureReply:
    """A typed, user-facing reply for a failed turn.

    Attributes:
        text: The visible, actionable message to deliver to the user. Includes
            next-step copy keyed by the failure class (how to re-authenticate,
            run onboarding, wait out a rate limit, etc.).
        reason_code: A machine-readable failure class (one of the ``REASON_*``
            constants) an operator/model can inspect and record.
        retryable: Whether the failure is worth retrying without user
            intervention (rate limit, overload, transient timeout).
    """

    text: str
    reason_code: str
    retryable: bool


def _reason_from_error(error: "PraisonAIError") -> str:
    """Derive a reason code from a :class:`PraisonAIError`.

    A missing/blank config key surfaces as ``missing_key`` (distinct from an
    expired credential) so the onboarding vs re-auth guidance stays precise.
    """
    category = getattr(error, "error_category", None) or "unknown"
    # A config error carrying a config_key is a *missing* credential/setting,
    # not a rejected one — steer the user to onboarding rather than re-auth.
    if getattr(error, "config_key", None) and category == "format_error":
        return REASON_MISSING_KEY
    return _ERROR_KIND_TO_REASON.get(category, REASON_UNKNOWN)


def _reason_from_outcome(outcome: "AgentRunOutcome") -> str:
    """Derive a reason code from an :class:`AgentRunOutcome`.

    Prefers a specific ``termination_reason`` recorded in the outcome context
    (budget/doom-loop/needs-help) before falling back to the error category and
    finally the coarse status.
    """
    context = getattr(outcome, "context", None) or {}
    termination = context.get("termination_reason") or context.get("termination")
    if termination is not None:
        key = getattr(termination, "value", termination)
        mapped = _TERMINATION_TO_REASON.get(str(key))
        if mapped is not None:
            return mapped

    category = getattr(outcome, "error_category", None)
    if category:
        mapped = _ERROR_KIND_TO_REASON.get(category)
        if mapped is not None:
            return mapped

    status = getattr(outcome, "status", None)
    if status == "timeout":
        return REASON_TIMEOUT
    if status == "cancelled":
        return REASON_CANCELLED
    if status == "invalid_output":
        return REASON_FORMAT_ERROR
    return REASON_UNKNOWN


def render_failure_reply(outcome: Any) -> FailureReply:
    """Map a run outcome or error to a visible, actionable :class:`FailureReply`.

    This is the failure-path counterpart of
    :func:`praisonaiagents.bots.silence.classify_final`: a single decision point
    so no adapter re-decides how a failure looks. It accepts either an
    :class:`~praisonaiagents.run_outcome.AgentRunOutcome` or a
    :class:`~praisonaiagents.errors.PraisonAIError` (duck-typed to avoid an
    import dependency), reuses the existing ``remediation_hint`` when present,
    and otherwise selects deterministic next-step copy keyed by the failure
    class.

    Args:
        outcome: An ``AgentRunOutcome``, a ``PraisonAIError`` (or subclass), or
            any object exposing ``error_category`` / ``status``. A plain string
            or unknown object degrades to a generic (but still visible)
            ``unknown`` reply rather than raising.

    Returns:
        A :class:`FailureReply` with actionable ``text``, a machine-readable
        ``reason_code`` and a ``retryable`` flag.
    """
    # Duck-type the two supported inputs without importing them (keeps this a
    # zero-dependency leaf like the other bot primitives).
    is_error = isinstance(outcome, BaseException)

    # Preserve an affirmative retryability signal from the source outcome (e.g.
    # AgentRunOutcome.is_retryable() is True for invalid_output) so a
    # reason-code that is not in the static ``_RETRYABLE_REASONS`` default does
    # not silently drop the retry affordance the outcome already promised.
    source_retryable = False

    if is_error:
        reason = _reason_from_error(outcome)  # type: ignore[arg-type]
        remediation = getattr(outcome, "remediation_hint", None)
    elif hasattr(outcome, "status") or hasattr(outcome, "error_category"):
        reason = _reason_from_outcome(outcome)
        context = getattr(outcome, "context", None) or {}
        remediation = context.get("remediation_hint")
        is_retryable = getattr(outcome, "is_retryable", None)
        if callable(is_retryable):
            try:
                source_retryable = bool(is_retryable())
            except Exception:
                source_retryable = False
    else:
        reason = REASON_UNKNOWN
        remediation = None

    text: Optional[str] = None
    if isinstance(remediation, str) and remediation.strip():
        # A concrete remediation hint (e.g. from PraisonAIConfigError) is the
        # most precise guidance available — prefer it over the static default.
        text = f"I couldn't complete that. {remediation.strip()}"
    if text is None:
        text = _REASON_TEXT.get(reason, _REASON_TEXT[REASON_UNKNOWN])

    return FailureReply(
        text=text,
        reason_code=reason,
        retryable=source_retryable or reason in _RETRYABLE_REASONS,
    )


__all__ = [
    "FailureReply",
    "render_failure_reply",
    "REASON_AUTH_EXPIRED",
    "REASON_AUTH_PERMANENT",
    "REASON_MISSING_KEY",
    "REASON_RATE_LIMIT",
    "REASON_OVERLOADED",
    "REASON_TIMEOUT",
    "REASON_BUDGET_EXHAUSTED",
    "REASON_DOOM_LOOP",
    "REASON_NEEDS_HELP",
    "REASON_CANCELLED",
    "REASON_CONTEXT_OVERFLOW",
    "REASON_MODEL_NOT_FOUND",
    "REASON_FORMAT_ERROR",
    "REASON_UNKNOWN",
]
