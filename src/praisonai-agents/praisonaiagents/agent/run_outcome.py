"""Canonical terminal-outcome contract for agent runs.

A single, closed description of *how* a run ended, produced once by the core
run and consumed everywhere. Long-running hosts (e.g. gateways/bots) can make
delivery/retry/DLQ/status decisions from one field instead of inferring the
terminal state from exception identity.

Precedence is explicit and sticky: a ``hard_timeout`` is never silently
downgraded by later cleanup. See ``RunOutcome.from_exception``.
"""

from dataclasses import dataclass
from typing import Optional
try:
    from typing import Literal
except ImportError:  # pragma: no cover - py<3.8 fallback
    Literal = None  # type: ignore

if Literal is not None:
    TerminalReason = Literal[
        "completed",
        "hard_timeout",
        "cancelled",
        "aborted",
        "failed",
        "content_filtered",
        "refused",
        "length_truncated",
    ]
else:  # pragma: no cover
    TerminalReason = str  # type: ignore

# Provider-side terminal reasons derived from the LLM ``finish_reason``/refusal
# signal. Additive and backward-compatible: absent/unknown finish reasons keep
# the existing ``completed|failed|...`` semantics unchanged.
PROVIDER_BLOCK_REASONS = ("content_filtered", "refused", "length_truncated")

# Precedence: higher wins and is sticky (a hard timeout is not downgraded).
# A specific provider block/refusal/truncation outranks a generic ``failed`` so
# the actionable reason is not masked, but stays below cancellation/timeout,
# which are host-level lifecycle signals.
_REASON_PRECEDENCE = {
    "completed": 0,
    "failed": 1,
    "content_filtered": 2,
    "refused": 2,
    "length_truncated": 2,
    "aborted": 3,
    "cancelled": 4,
    "hard_timeout": 5,
}


@dataclass(frozen=True)
class RunOutcome:
    """Closed, canonical description of how an agent run ended.

    Attributes:
        reason: One of ``completed | hard_timeout | cancelled | aborted | failed``.
        output: Partial or final text, if any.
        error: Redacted message when ``reason == "failed"``.
    """

    reason: "TerminalReason"
    output: Optional[str] = None
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        """True only when the run completed normally."""
        return self.reason == "completed"

    @classmethod
    def completed(cls, output: Optional[str] = None) -> "RunOutcome":
        return cls(reason="completed", output=output)

    @classmethod
    def from_exception(
        cls, exc: BaseException, output: Optional[str] = None
    ) -> "RunOutcome":
        """Normalise a raised exception into a canonical terminal outcome.

        Maps well-known exception types to their terminal reason. Anything
        unrecognised is treated as ``failed`` with a redacted message.

        Note on ``hard_timeout``: the run-level budget is the authoritative
        source of ``hard_timeout`` and is applied explicitly by the caller
        (see ``_astart_with_outcome``). A bare ``asyncio.TimeoutError`` reaching
        this normaliser is a *nested* operation timeout (e.g. a handoff/tool that
        exhausted its own budget while the run budget remained) and is therefore
        classified as ``failed`` — not silently promoted to a run-budget
        ``hard_timeout``, which would drive the wrong host retry/DLQ decision.
        Real cooperative cancellation is intercepted and re-raised by the run
        wrapper (see ``_astart_with_outcome``) *before* it reaches this
        normaliser, so host shutdown is honoured. A supersede/interrupt named
        error that does surface here is a domain "cancelled" outcome.
        """
        import asyncio

        if _name_matches(exc, ("hardtimeout", "runtimeout", "budgettimeout")):
            return cls(reason="hard_timeout", output=output)
        if isinstance(exc, asyncio.CancelledError) or _name_matches(
            exc, ("supersed", "interrupt", "cancelled")
        ):
            return cls(reason="cancelled", output=output)
        if _name_matches(exc, ("abort", "drain", "shutdown")):
            return cls(reason="aborted", output=output)
        return cls(reason="failed", output=output, error=str(exc))


def _name_matches(exc: BaseException, needles: tuple) -> bool:
    name = type(exc).__name__.lower()
    return any(n in name for n in needles)


def classify_finish_reason(finish_reason, refusal=None):
    """Map a provider ``finish_reason``/refusal signal to a terminal reason.

    Returns one of ``content_filtered | refused | length_truncated`` when the
    provider blocked/refused/truncated the turn, or ``None`` for a normal stop
    (``None``/``"stop"``) or any unrecognised value — so unknown finish reasons
    behave exactly as today. Additive and zero-cost on the success path.
    """
    if refusal:
        return "refused"
    if not finish_reason:
        return None
    fr = str(finish_reason).lower()
    if fr in ("stop", "tool_calls", "function_call"):
        return None
    if "content_filter" in fr or fr == "content_filtered":
        return "content_filtered"
    if "refus" in fr:
        return "refused"
    if fr == "length" or "max_tokens" in fr or "truncat" in fr:
        return "length_truncated"
    return None
