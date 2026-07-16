"""
PromptOptimizer - automatic optimisation of an agent's instructions against an eval.

Given an agent, a small eval set, and a scorer (LLM ``Judge`` by default or a
user-supplied numeric metric), the optimiser generates N instruction candidates,
evaluates each candidate over the eval set, keeps the highest-scoring one, and
(optionally) writes the winning instructions back to ``agent.instructions``.

This is the bounded "keep-the-best prompt" slice — it does NOT do tree/beam
search over code variants or an agent-rewrites-its-own-harness loop.

Example:
    from praisonaiagents import Agent
    from praisonaiagents.eval import PromptOptimizer

    agent = Agent(name="summariser", instructions="Summarise the input.")
    result = PromptOptimizer(
        agent=agent,
        evalset=[("summarise X", gold_x), ("summarise Y", gold_y)],
        metric=rouge_l,          # numeric metric, or omit to use the LLM Judge
        n_candidates=6,
    ).optimize()
    print(result.best_score, result.best_instructions)
"""

from praisonaiagents._logging import get_logger
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

if TYPE_CHECKING:
    from ..agent.agent import Agent

logger = get_logger(__name__)

# An eval case is (prompt, expected). ``expected`` may be None when using a
# Judge with only criteria.
EvalCase = Tuple[str, Any]


@dataclass
class OptimizeResult:
    """Result of a prompt-optimisation run.

    Attributes:
        best_instructions: The highest-scoring instructions found.
        best_score: The aggregate score of the winning instructions.
        base_score: The aggregate score of the original instructions.
        trials: List of ``(instructions, score)`` for every candidate tried,
            including the base instructions.
        applied: Whether the winning instructions were written back to the agent.
    """
    best_instructions: str
    best_score: float
    base_score: float = 0.0
    trials: List[Tuple[str, float]] = field(default_factory=list)
    applied: bool = False

    @property
    def improved(self) -> bool:
        """True when the best candidate scored strictly higher than the base."""
        return self.best_score > self.base_score


class PromptOptimizer:
    """Optimise an agent's instructions against an eval set, keeping the best.

    Args:
        agent: The Agent whose ``instructions`` will be optimised.
        evalset: List of ``(prompt, expected)`` cases to score candidates on.
        scorer: Optional custom ``Judge`` instance (defaults to a new ``Judge``).
            Ignored when ``metric`` is provided.
        metric: Optional numeric metric ``(output, expected) -> float``. When
            set, empirical scoring replaces the LLM Judge.
        criteria: Optional criteria passed to the default Judge.
        n_candidates: Number of instruction candidates to generate (default: 6).
        model: LLM model used to propose candidates / judge (default: gpt-4o-mini).
        apply: Write the winning instructions back to the agent (default: True).
    """

    def __init__(
        self,
        agent: "Agent",
        evalset: List[EvalCase],
        *,
        scorer: Optional[Any] = None,
        metric: Optional[Callable[[str, Any], float]] = None,
        criteria: str = "",
        n_candidates: int = 6,
        model: str = "gpt-4o-mini",
        apply: bool = True,
    ):
        if not evalset:
            raise ValueError("evalset must contain at least one (prompt, expected) case")
        self.agent = agent
        self.evalset = list(evalset)
        self._scorer = scorer
        self.metric = metric
        self.criteria = criteria
        self.n_candidates = n_candidates
        self.model = model
        self.apply = apply
        self.trials: List[Tuple[str, float]] = []

    @property
    def scorer(self):
        """Lazy-load a Judge for scoring (only when no numeric metric is set)."""
        if self.metric is not None:
            return None
        if self._scorer is None:
            from .judge import Judge
            self._scorer = Judge(criteria=self.criteria, model=self.model)
        return self._scorer

    def _score_one(self, output: str, expected: Any) -> float:
        """Score a single output against its expected value."""
        if self.metric is not None:
            return float(self.metric(output, expected))
        result = self.scorer.run(output=output, expected=expected, criteria=self.criteria)
        return float(result.score)

    def _score_instructions(self, instructions: str) -> float:
        """Run the agent (with ``instructions``) over the eval set and aggregate.

        Temporarily swaps ``agent.instructions``, runs each prompt, scores it,
        and returns the mean score. Always restores the original instructions.
        """
        original = self.agent.instructions
        scores: List[float] = []
        try:
            self.agent.instructions = instructions
            for prompt, expected in self.evalset:
                output = str(self.agent.chat(prompt))
                scores.append(self._score_one(output, expected))
        finally:
            self.agent.instructions = original
        return sum(scores) / len(scores) if scores else 0.0

    def _lowest_scoring_examples(self, instructions: str, limit: int = 2) -> List[str]:
        """Return prompts where ``instructions`` scored worst (reflective signal)."""
        original = self.agent.instructions
        scored: List[Tuple[float, str]] = []
        try:
            self.agent.instructions = instructions
            for prompt, expected in self.evalset:
                output = str(self.agent.chat(prompt))
                scored.append((self._score_one(output, expected), prompt))
        finally:
            self.agent.instructions = original
        scored.sort(key=lambda x: x[0])
        return [p for _, p in scored[:limit]]

    def _propose_variants(self, base: str) -> List[str]:
        """Ask an auxiliary LLM to rewrite ``base`` into diverse candidates."""
        weak = self._lowest_scoring_examples(base)
        weak_block = ""
        if weak:
            weak_block = "\n\nThese example prompts scored poorly; address them:\n" + \
                "\n".join(f"- {p}" for p in weak)
        proposal_prompt = (
            "You are optimising an AI agent's system instructions. "
            f"Rewrite the instructions below into {self.n_candidates} distinct, "
            "improved variants. Each variant must be a complete, standalone set of "
            "instructions that stays faithful to the original intent while being "
            "clearer and more effective. Return one variant per line, no numbering, "
            "no commentary.\n\n"
            f"Current instructions:\n{base}{weak_block}"
        )
        from ..agent.agent import Agent
        proposer = Agent(
            name="prompt-optimizer",
            instructions="You rewrite system prompts into improved variants.",
            llm=self.model,
        )
        response = str(proposer.chat(proposal_prompt) or "")
        variants = [line.strip(" -\t") for line in response.splitlines() if line.strip()]
        seen = set()
        unique: List[str] = []
        for v in variants:
            if v and v != base and v not in seen:
                seen.add(v)
                unique.append(v)
        return unique[: self.n_candidates]

    def optimize(self) -> OptimizeResult:
        """Generate candidates, keep the best, and (optionally) apply it."""
        base = self.agent.instructions or ""
        base_score = self._score_instructions(base)
        self.trials = [(base, base_score)]
        best_instructions, best_score = base, base_score

        for candidate in self._propose_variants(base):
            score = self._score_instructions(candidate)
            self.trials.append((candidate, score))
            if score > best_score:
                best_instructions, best_score = candidate, score

        applied = False
        if self.apply and best_instructions != base:
            self.agent.instructions = best_instructions
            applied = True

        return OptimizeResult(
            best_instructions=best_instructions,
            best_score=best_score,
            base_score=base_score,
            trials=list(self.trials),
            applied=applied,
        )


__all__ = [
    "PromptOptimizer",
    "OptimizeResult",
]
