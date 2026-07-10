"""
GoalEngineer - the core Goal Engineering entry point.

Goal Engineering is the systematic practice of turning a vague objective into a
structured, measurable :class:`Goal` (statement + weighted success criteria +
constraints), then verifying an output against it.

It complements Context / Harness / Loop (CHL) engineering by making the *goal*
itself an explicit, testable artifact.

Example:
    >>> from praisonaiagents.goal import GoalEngineer
    >>> engineer = GoalEngineer(auto_decompose=False)
    >>> goal = engineer.engineer("Summarise the report in under 100 words")
    >>> goal.add_criterion("Summary is under 100 words")
    >>> goal.add_criterion("Key findings are preserved")
    >>> result = engineer.verify(goal, "A concise summary...")
    >>> print(result.score, result.achieved)

Zero performance impact: heavy LLM helpers are imported lazily inside methods.
"""

import json
import re
from typing import Any, List, Optional

from praisonaiagents._logging import get_logger

from .config import GoalConfig
from .models import Goal, GoalVerificationResult, SuccessCriterion

logger = get_logger(__name__)


_DECOMPOSE_PROMPT = """You are a goal-engineering assistant. Break the following \
goal into at most {max_criteria} concise, measurable success criteria.

GOAL: {statement}

Return ONLY a JSON array of short strings, e.g. ["criterion 1", "criterion 2"].
Each criterion must be objectively checkable."""


class GoalEngineer:
    """
    Engineers structured, measurable goals and verifies outputs against them.

    Args:
        model: LLM model for decomposition/verification (overrides config).
        max_criteria: Max number of success criteria to generate.
        threshold: Score (0-10) at/above which a goal is achieved.
        auto_decompose: Auto-generate criteria via the LLM when engineering.
        config: A full :class:`GoalConfig` (takes precedence over kwargs).
        verbose: Enable verbose logging.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        max_criteria: Optional[int] = None,
        threshold: Optional[float] = None,
        auto_decompose: Optional[bool] = None,
        config: Optional[GoalConfig] = None,
        verbose: bool = False,
    ):
        self.config = config or GoalConfig()
        if model is not None:
            self.config.model = model
        if max_criteria is not None:
            self.config.max_criteria = max_criteria
        if threshold is not None:
            self.config.threshold = threshold
        if auto_decompose is not None:
            self.config.auto_decompose = auto_decompose
        if verbose:
            self.config.verbose = verbose

    def engineer(
        self,
        statement: str,
        criteria: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
    ) -> Goal:
        """
        Build a structured :class:`Goal` from a plain statement.

        If ``criteria`` are provided they are used directly. Otherwise, when
        ``auto_decompose`` is enabled, the LLM proposes measurable criteria.
        """
        goal = Goal(statement=statement, constraints=list(constraints or []))

        if criteria:
            for description in criteria:
                goal.add_criterion(description)
        elif self.config.auto_decompose:
            for description in self._decompose(statement):
                goal.add_criterion(description)

        if self.config.verbose:
            logger.info(
                "Engineered goal %s with %d criteria",
                goal.id,
                len(goal.criteria),
            )
        return goal

    def _decompose(self, statement: str) -> List[str]:
        """Use the LLM to decompose a statement into success criteria."""
        prompt = _DECOMPOSE_PROMPT.format(
            max_criteria=self.config.max_criteria,
            statement=statement,
        )
        try:
            from ..llm.llm import LLM

            response = LLM(model=self.config.model).get_response(
                prompt=prompt,
                temperature=0.1,
                verbose=self.config.verbose,
            )
        except Exception as exc:  # pragma: no cover - network/optional dep
            logger.warning("Goal decomposition failed: %s", exc)
            return []

        return self._parse_criteria(response)

    @staticmethod
    def _parse_criteria(response: Any) -> List[str]:
        """Parse an LLM response into a list of criterion strings."""
        text = response if isinstance(response, str) else str(response)
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                items = json.loads(match.group(0))
                return [str(i).strip() for i in items if str(i).strip()]
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: split lines/bullets.
        lines = []
        for line in text.splitlines():
            cleaned = line.strip().lstrip("-*0123456789. ").strip()
            if cleaned:
                lines.append(cleaned)
        return lines

    def verify(self, goal: Goal, output: Any) -> GoalVerificationResult:
        """
        Verify an ``output`` against a ``goal`` using LLM-as-judge.

        Reuses the unified :class:`~praisonaiagents.eval.Judge` (DRY). Falls back
        to a neutral result if the judge is unavailable.
        """
        criteria_block = "\n".join(
            f"- {c.description}" for c in goal.criteria
        ) or "- Achieves the stated goal"

        criteria_text = (
            f"Evaluate whether the output achieves this goal.\n"
            f"Goal: {goal.statement}\n"
            f"Success criteria:\n{criteria_block}"
        )
        if goal.constraints:
            constraints_block = "\n".join(f"- {c}" for c in goal.constraints)
            criteria_text += f"\nConstraints (must not be violated):\n{constraints_block}"

        score = 0.0
        reasoning = ""
        try:
            from ..eval import Judge

            judge_result = Judge(
                model=self.config.model,
                criteria=criteria_text,
            ).run(output=output)
            score = float(getattr(judge_result, "score", 0.0) or 0.0)
            reasoning = getattr(judge_result, "reasoning", "") or ""
        except Exception as exc:  # pragma: no cover - network/optional dep
            logger.warning("Goal verification failed: %s", exc)
            reasoning = f"Verification unavailable: {exc}"

        achieved = score >= self.config.threshold
        status = "met" if achieved else ("unmet" if reasoning else "pending")
        for criterion in goal.criteria:
            criterion.status = status

        return GoalVerificationResult(
            goal_id=goal.id,
            score=score,
            achieved=achieved,
            criteria=list(goal.criteria),
            reasoning=reasoning,
        )
