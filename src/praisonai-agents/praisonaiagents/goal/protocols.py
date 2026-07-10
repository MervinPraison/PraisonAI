"""
Protocols for Goal Engineering.

Defines the extension contracts for goal decomposition and verification.
Protocol-driven: implement any of these for custom behavior.
"""

from typing import Any, List, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Goal, SuccessCriterion, GoalVerificationResult


@runtime_checkable
class GoalDecomposerProtocol(Protocol):
    """Contract for turning a goal statement into measurable success criteria."""

    def decompose(self, goal: "Goal") -> List["SuccessCriterion"]:
        """Return an ordered list of success criteria for the goal."""
        ...


@runtime_checkable
class GoalVerifierProtocol(Protocol):
    """Contract for verifying whether an output satisfies a goal."""

    def verify(self, goal: "Goal", output: Any) -> "GoalVerificationResult":
        """Score the output against the goal's success criteria."""
        ...


@runtime_checkable
class GoalEngineerProtocol(Protocol):
    """Contract for the full goal-engineering lifecycle."""

    def engineer(self, statement: str) -> "Goal":
        """Build a structured, decomposed Goal from a plain statement."""
        ...

    def verify(self, goal: "Goal", output: Any) -> "GoalVerificationResult":
        """Verify an output against an engineered goal."""
        ...
