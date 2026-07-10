"""
Data models for Goal Engineering.

A ``Goal`` is a structured, measurable representation of what an agent should
achieve. It is decomposed into ``SuccessCriterion`` items that can be tracked
and verified independently.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


CriterionStatus = Literal["pending", "met", "unmet"]


@dataclass
class SuccessCriterion:
    """
    A single measurable condition that contributes to achieving a goal.

    Attributes:
        description: What must be true for this criterion to be met.
        id: Unique identifier.
        weight: Relative importance when scoring the goal (default 1.0).
        status: Current status (pending, met, unmet).
        notes: Optional notes from verification.
    """

    description: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    weight: float = 1.0
    status: CriterionStatus = "pending"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "weight": self.weight,
            "status": self.status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SuccessCriterion":
        return cls(
            description=data.get("description", ""),
            id=data.get("id", str(uuid.uuid4())[:8]),
            weight=float(data.get("weight", 1.0)),
            status=data.get("status", "pending"),
            notes=data.get("notes", ""),
        )


@dataclass
class Goal:
    """
    A structured, measurable goal for an agent.

    Attributes:
        statement: The high-level objective in natural language.
        id: Unique identifier.
        criteria: Ordered list of success criteria.
        constraints: Hard constraints that must never be violated.
        metadata: Free-form metadata (domain, owner, etc.).
    """

    statement: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    criteria: List[SuccessCriterion] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_criterion(
        self, description: str, weight: float = 1.0
    ) -> SuccessCriterion:
        """Add a success criterion and return it."""
        criterion = SuccessCriterion(description=description, weight=weight)
        self.criteria.append(criterion)
        return criterion

    @property
    def progress(self) -> float:
        """Fraction of weighted criteria currently met (0.0 - 1.0)."""
        if not self.criteria:
            return 0.0
        total = sum(c.weight for c in self.criteria) or 1.0
        met = sum(c.weight for c in self.criteria if c.status == "met")
        return met / total

    @property
    def is_achieved(self) -> bool:
        """True when there is at least one criterion and all are met."""
        return bool(self.criteria) and all(
            c.status == "met" for c in self.criteria
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "criteria": [c.to_dict() for c in self.criteria],
            "constraints": list(self.constraints),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        return cls(
            statement=data.get("statement", ""),
            id=data.get("id", str(uuid.uuid4())[:8]),
            criteria=[
                SuccessCriterion.from_dict(c) for c in data.get("criteria", [])
            ],
            constraints=list(data.get("constraints", [])),
            metadata=dict(data.get("metadata", {})),
        )

    def to_prompt(self) -> str:
        """Render the goal as an instruction block for an agent prompt."""
        lines = [f"Goal: {self.statement}"]
        if self.criteria:
            lines.append("Success criteria:")
            for c in self.criteria:
                lines.append(f"  - {c.description}")
        if self.constraints:
            lines.append("Constraints (must never be violated):")
            for constraint in self.constraints:
                lines.append(f"  - {constraint}")
        return "\n".join(lines)


@dataclass
class GoalVerificationResult:
    """
    Outcome of verifying an output against a goal.

    Attributes:
        goal_id: The verified goal's id.
        score: Overall score in the 0.0 - 10.0 range.
        achieved: Whether the goal is considered achieved.
        criteria: The (updated) criteria with their statuses.
        reasoning: Explanation of the verification.
    """

    goal_id: str
    score: float
    achieved: bool
    criteria: List[SuccessCriterion] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "score": self.score,
            "achieved": self.achieved,
            "criteria": [c.to_dict() for c in self.criteria],
            "reasoning": self.reasoning,
        }
