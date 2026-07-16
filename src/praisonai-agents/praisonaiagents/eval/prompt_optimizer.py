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

import contextlib
import math
from praisonaiagents._logging import get_logger
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Generator, List, Optional, Tuple

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

    _DELIMITER = "==="

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
            value = float(self.metric(output, expected))
        else:
            result = self.scorer.run(output=output, expected=expected, criteria=self.criteria)
            value = float(result.score)
        # Non-finite scores (NaN/inf) break ``max()`` and threshold logic; treat
        # them as the worst possible score so they never win selection.
        if not math.isfinite(value):
            logger.warning("Scorer returned non-finite value %r; treating as 0.0", value)
            return 0.0
        return value

    @contextlib.contextmanager
    def _applied(self, instructions: str) -> Generator[None, None, None]:
        """Temporarily make ``instructions`` the agent's *effective* prompt.

        The agent's system prompt is derived from ``goal``/``backstory`` (seeded
        from ``instructions`` at construction) and is cached; swapping only
        ``instructions`` would leave chat behaviour unchanged. This swaps all
        three fields, clears the system-prompt cache so the change takes effect,
        and isolates chat history so eval turns never pollute the live agent.
        Everything is restored on exit, even on error.
        """
        agent = self.agent
        original = (
            getattr(agent, "instructions", None),
            getattr(agent, "goal", None),
            getattr(agent, "backstory", None),
        )
        cache = getattr(agent, "_system_prompt_cache", None)
        try:
            agent.instructions = instructions
            if hasattr(agent, "goal"):
                agent.goal = instructions
            if hasattr(agent, "backstory"):
                agent.backstory = instructions
            if cache is not None:
                cache.clear()
            ephemeral = getattr(agent, "ephemeral", None)
            if callable(ephemeral):
                with ephemeral():
                    yield
            else:
                yield
        finally:
            agent.instructions, goal, backstory = original[0], original[1], original[2]
            if goal is not None and hasattr(agent, "goal"):
                agent.goal = goal
            if backstory is not None and hasattr(agent, "backstory"):
                agent.backstory = backstory
            if cache is not None:
                cache.clear()

    def _score_instructions(self, instructions: str) -> float:
        """Run the agent (with ``instructions``) over the eval set and aggregate.

        Temporarily makes ``instructions`` the agent's effective prompt, runs
        each prompt, scores it, and returns the mean score. Always restores the
        original agent state.
        """
        scores: List[float] = []
        with self._applied(instructions):
            for prompt, expected in self.evalset:
                output = str(self.agent.chat(prompt))
                scores.append(self._score_one(output, expected))
        return sum(scores) / len(scores) if scores else 0.0

    def _lowest_scoring_examples(self, instructions: str, limit: int = 2) -> List[str]:
        """Return prompts where ``instructions`` scored worst (reflective signal)."""
        scored: List[Tuple[float, str]] = []
        with self._applied(instructions):
            for prompt, expected in self.evalset:
                output = str(self.agent.chat(prompt))
                scored.append((self._score_one(output, expected), prompt))
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
            "instructions (which may span multiple lines) that stays faithful to "
            "the original intent while being clearer and more effective. Separate "
            f"each variant with a line containing only {self._DELIMITER!r}. "
            "No numbering, no commentary.\n\n"
            f"Current instructions:\n{base}{weak_block}"
        )
        from ..agent.agent import Agent
        proposer = Agent(
            name="prompt-optimizer",
            instructions="You rewrite system prompts into improved variants.",
            llm=self.model,
        )
        response = str(proposer.chat(proposal_prompt) or "")
        variants = self._split_variants(response)
        seen = set()
        unique: List[str] = []
        for v in variants:
            if v and v != base and v not in seen:
                seen.add(v)
                unique.append(v)
        return unique[: self.n_candidates]

    def _split_variants(self, response: str) -> List[str]:
        """Parse the proposer response into complete (possibly multiline) variants.

        Splits on the explicit delimiter when present, otherwise falls back to
        blank-line-separated blocks, so a multiline prompt is kept intact rather
        than treated as many single-line fragments.
        """
        text = response.strip()
        if not text:
            return []
        if self._DELIMITER in text:
            blocks = text.split(self._DELIMITER)
        else:
            import re
            blocks = re.split(r"\n\s*\n", text)
        return [b.strip().strip("-").strip() for b in blocks if b.strip()]

    def _apply_permanently(self, instructions: str) -> None:
        """Write winning instructions to the fields that drive the system prompt.

        The chat system prompt is built from ``goal``/``backstory`` (both seeded
        from ``instructions`` at construction) and cached; writing all three and
        clearing the cache ensures the applied instructions actually take effect.
        """
        agent = self.agent
        agent.instructions = instructions
        if hasattr(agent, "goal"):
            agent.goal = instructions
        if hasattr(agent, "backstory"):
            agent.backstory = instructions
        cache = getattr(agent, "_system_prompt_cache", None)
        if cache is not None:
            cache.clear()

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
            self._apply_permanently(best_instructions)
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
