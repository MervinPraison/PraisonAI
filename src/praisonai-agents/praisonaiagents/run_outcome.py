"""
Structured run outcome types for agent execution results.

Provides a typed, closed discriminant union for agent run completions,
task validation outcomes, and handoff results across the SDK.

Replaces freeform string-based validation outcomes with type-safe status
values that enable exhaustive error handling and structured metadata.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional, Dict, Any


# Typed status discriminant union for agent run outcomes
RunStatus = Literal[
    "success",        # Execution completed successfully
    "failure",        # General failure (non-retryable logic error)
    "timeout",        # Operation timed out (may be retryable)
    "cancelled",      # Execution was cancelled (external signal)
    "invalid_output"  # Output validation failed (may be retryable)
]


class TerminationReason(str, Enum):
    """Typed terminal reasons for an autonomous run.

    String *values* are identical to the free strings historically emitted by
    ``run_autonomous``/``AutonomyResult.completion_reason`` so existing callers
    that string-match keep working (``TerminationReason.GOAL_MET == "goal"``).

    Subclassing ``str`` keeps equality/serialisation backward compatible; the
    new ``BUDGET_EXHAUSTED`` value is the spend kill-switch terminal state.
    """
    GOAL_MET = "goal"
    TOOL_COMPLETION = "tool_completion"
    PROMISE = "promise"
    NO_TOOL_CALLS = "no_tool_calls"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DOOM_LOOP = "doom_loop"
    NEEDS_HELP = "needs_help"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    ERROR = "error"


# Map a TerminationReason to the closed AgentRunOutcome RunStatus vocabulary so
# autonomous runs and task validation share one terminal terminology.
_TERMINATION_TO_RUN_STATUS: Dict[str, RunStatus] = {
    TerminationReason.GOAL_MET.value: "success",
    TerminationReason.TOOL_COMPLETION.value: "success",
    TerminationReason.PROMISE.value: "success",
    TerminationReason.NO_TOOL_CALLS.value: "success",
    TerminationReason.MAX_ITERATIONS.value: "failure",
    TerminationReason.TIMEOUT.value: "timeout",
    TerminationReason.BUDGET_EXHAUSTED.value: "failure",
    TerminationReason.DOOM_LOOP.value: "failure",
    TerminationReason.NEEDS_HELP.value: "failure",
    TerminationReason.INTERRUPTED.value: "cancelled",
    TerminationReason.CANCELLED.value: "cancelled",
    TerminationReason.ERROR.value: "failure",
}


def termination_to_run_status(reason: Any) -> RunStatus:
    """Map a ``TerminationReason`` (or its string value) to a ``RunStatus``.

    Unknown reasons fall back to ``"failure"``.
    """
    key = reason.value if isinstance(reason, TerminationReason) else str(reason)
    return _TERMINATION_TO_RUN_STATUS.get(key, "failure")


@dataclass
class AgentRunOutcome:
    """
    Structured outcome for agent execution, validation, and handoff operations.
    
    Replaces freeform string parsing with typed status values that callers
    can match exhaustively. Provides structured metadata for debugging and
    retry policies.
    
    Examples:
        Success case:
        >>> outcome = AgentRunOutcome(status="success", output="Task completed")
        >>> assert outcome.is_success()
        
        Validation failure:
        >>> outcome = AgentRunOutcome(
        ...     status="invalid_output", 
        ...     error="Output format is invalid",
        ...     error_category="validation"
        ... )
        >>> assert outcome.is_retryable()
        
        Timeout with context:
        >>> outcome = AgentRunOutcome(
        ...     status="timeout",
        ...     error="Agent timed out after 30s",
        ...     elapsed_s=30.0,
        ...     agent_name="researcher"
        ... )
    """
    
    status: RunStatus
    """Typed status discriminant - exhaustively matchable."""
    
    output: Optional[str] = None
    """Successful execution output or partial result."""
    
    error: Optional[str] = None
    """Error message for non-successful outcomes."""
    
    error_category: Optional[str] = None
    """Error category from PraisonAIError.error_category if applicable."""
    
    elapsed_s: float = 0.0
    """Execution duration in seconds."""
    
    agent_name: Optional[str] = None
    """Name of the agent that produced this outcome."""
    
    run_id: Optional[str] = None
    """Unique identifier for this execution run."""
    
    context: Optional[Dict[str, Any]] = None
    """Additional structured metadata."""

    _VALID_STATUSES = {"success", "failure", "timeout", "cancelled", "invalid_output"}

    def __post_init__(self) -> None:
        if self.status not in self._VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. "
                "Use one of: success, failure, timeout, cancelled, invalid_output."
            )
    
    def is_success(self) -> bool:
        """Check if the outcome represents successful completion."""
        return self.status == "success"
    
    def is_failure(self) -> bool:
        """Check if the outcome represents any kind of failure."""
        return self.status != "success"
    
    def is_retryable(self) -> bool:
        """
        Check if this outcome represents a potentially retryable failure.
        
        Based on the status type:
        - timeout: Generally retryable with longer timeout
        - invalid_output: May be retryable with different prompt/validation
        - failure: Usually not retryable (logic error)
        - cancelled: Not retryable (external signal)
        """
        return self.status in ("timeout", "invalid_output")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization or logging."""
        return {
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "error_category": self.error_category,
            "elapsed_s": self.elapsed_s,
            "agent_name": self.agent_name,
            "run_id": self.run_id,
            "context": self.context,
        }
    
    @classmethod
    def success(
        cls,
        output: str,
        elapsed_s: float = 0.0,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "AgentRunOutcome":
        """Create a successful outcome."""
        return cls(
            status="success",
            output=output,
            elapsed_s=elapsed_s,
            agent_name=agent_name,
            run_id=run_id,
            context=context,
        )
    
    @classmethod
    def failure(
        cls,
        error: str,
        error_category: Optional[str] = None,
        elapsed_s: float = 0.0,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "AgentRunOutcome":
        """Create a general failure outcome."""
        return cls(
            status="failure",
            error=error,
            error_category=error_category,
            elapsed_s=elapsed_s,
            agent_name=agent_name,
            run_id=run_id,
            context=context,
        )
    
    @classmethod
    def timeout(
        cls,
        error: str = "Operation timed out",
        elapsed_s: float = 0.0,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "AgentRunOutcome":
        """Create a timeout outcome."""
        return cls(
            status="timeout",
            error=error,
            error_category="timeout",
            elapsed_s=elapsed_s,
            agent_name=agent_name,
            run_id=run_id,
            context=context,
        )
    
    @classmethod
    def cancelled(
        cls,
        error: str = "Operation was cancelled",
        elapsed_s: float = 0.0,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "AgentRunOutcome":
        """Create a cancelled outcome."""
        return cls(
            status="cancelled",
            error=error,
            error_category="cancelled",
            elapsed_s=elapsed_s,
            agent_name=agent_name,
            run_id=run_id,
            context=context,
        )
    
    @classmethod
    def invalid_output(
        cls,
        error: str,
        elapsed_s: float = 0.0,
        agent_name: Optional[str] = None,
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> "AgentRunOutcome":
        """Create an invalid output outcome."""
        return cls(
            status="invalid_output",
            error=error,
            error_category="validation",
            elapsed_s=elapsed_s,
            agent_name=agent_name,
            run_id=run_id,
            context=context,
        )


def validate_decision_string(decision_str: str) -> RunStatus:
    """
    Convert legacy validation decision strings to typed RunStatus.
    
    Provides backward compatibility during migration from the legacy
    VALIDATION_FAILURE_DECISIONS string list to typed outcomes.
    
    Args:
        decision_str: Legacy validation decision string (lowercased)
        
    Returns:
        Corresponding RunStatus value
        
    Examples:
        >>> validate_decision_string("success")
        "success"
        >>> validate_decision_string("invalid")  
        "invalid_output"
        >>> validate_decision_string("timeout")
        "timeout"
    """
    if decision_str is None:
        return "failure"
    if not isinstance(decision_str, str):
        raise TypeError(
            f"decision_str must be str, got {type(decision_str).__name__}. "
            "Pass the raw validator text output as a string."
        )
    decision_lower = decision_str.lower().strip()
    
    # Map legacy validation decision strings to typed status
    if decision_lower in ("success", "successful", "valid", "approved", "accept", "accepted", "complete", "completed"):
        return "success"
    elif decision_lower in ("timeout", "timed out"):
        return "timeout"
    elif decision_lower in ("cancelled", "canceled", "aborted"):
        return "cancelled"
    elif decision_lower in ("invalid", "retry", "failed", "error", "unsuccessful", "fail", "errors", "reject", "rejected", "incomplete"):
        return "invalid_output"
    else:
        # Unknown decision string - treat as general failure
        return "failure"


# Backward compatibility export
__all__ = [
    "AgentRunOutcome",
    "RunStatus",
    "TerminationReason",
    "termination_to_run_status",
    "validate_decision_string",
]