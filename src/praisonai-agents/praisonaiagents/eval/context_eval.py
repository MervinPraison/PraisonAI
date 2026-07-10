"""
Context evaluator for PraisonAI Agents evaluation framework.

Scores Context Engineering behaviour from the core SDK without requiring the
``praisonai`` wrapper or a live LLM. This migrates the context-flow scoring
algorithm previously trapped in ``praisonai/replay/judge.py``
(``_evaluate_context_flow``) so SDK-only consumers and CI pipelines can measure:

    - Multi-agent handoff fidelity (how much of agent N's output reaches N+1)
    - Token-budget compliance against a budget ledger

Example:
    >>> from praisonaiagents.eval import ContextEvaluator
    >>> evaluator = ContextEvaluator(
    ...     trace_events=events,
    ...     agent_order=["researcher", "writer"],
    ... )
    >>> result = evaluator.run(print_summary=True)
    >>> print(result.overall_score)
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .base import BaseEvaluator


@dataclass
class ContextHandoffResult:
    """Score for context flow between two consecutive agents."""

    from_agent: str
    to_agent: str
    context_passed_score: float  # 1-10: How much context was passed?
    context_relevance_score: float  # 1-10: Was the right context passed?
    content_loss_detected: bool  # Was important content lost?
    lost_content_summary: str = ""
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BudgetComplianceResult:
    """Score for token-budget adherence."""

    agent_name: str
    used_tokens: int
    budget_tokens: int
    within_budget: bool
    compliance_score: float  # 1-10: closer to budget without exceeding = higher
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContextEvalResult:
    """Aggregated result from a ContextEvaluator run."""

    handoffs: List[ContextHandoffResult] = field(default_factory=list)
    budgets: List[BudgetComplianceResult] = field(default_factory=list)
    eval_id: str = ""
    name: str = ""

    @property
    def handoff_score(self) -> float:
        """Average handoff (context-passed) score across all handoffs (0-10)."""
        if not self.handoffs:
            return 0.0
        return sum(h.context_passed_score for h in self.handoffs) / len(self.handoffs)

    @property
    def budget_score(self) -> float:
        """Average budget-compliance score across all ledger entries (0-10)."""
        if not self.budgets:
            return 0.0
        return sum(b.compliance_score for b in self.budgets) / len(self.budgets)

    @property
    def overall_score(self) -> float:
        """Overall context score (0-10).

        Averages handoff and budget scores when both are present; otherwise
        falls back to whichever dimension was evaluated.
        """
        scores = []
        if self.handoffs:
            scores.append(self.handoff_score)
        if self.budgets:
            scores.append(self.budget_score)
        if not scores:
            return 0.0
        return sum(scores) / len(scores)

    @property
    def content_loss_detected(self) -> bool:
        """True if any handoff lost meaningful content."""
        return any(h.content_loss_detected for h in self.handoffs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eval_id": self.eval_id,
            "name": self.name,
            "handoff_score": self.handoff_score,
            "budget_score": self.budget_score,
            "overall_score": self.overall_score,
            "content_loss_detected": self.content_loss_detected,
            "handoffs": [h.to_dict() for h in self.handoffs],
            "budgets": [b.to_dict() for b in self.budgets],
        }


class ContextEvaluator(BaseEvaluator):
    """Score context budget compliance and multi-agent handoff fidelity.

    This evaluator is LLM-free and dependency-free: it inspects a trace of
    events (or plain dicts) and an optional budget ledger to produce
    deterministic scores suitable for CI gates.
    """

    def __init__(
        self,
        trace_events: Optional[List[Any]] = None,
        agent_order: Optional[List[str]] = None,
        budget_ledger: Optional[List[Dict[str, Any]]] = None,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        """
        Initialize the context evaluator.

        Args:
            trace_events: List of trace events (objects with ``event_type``/
                ``agent_name``/``data`` attributes, or equivalent dicts).
            agent_order: Ordered list of agent names describing the handoff chain.
            budget_ledger: Optional list of ``{"agent_name", "used_tokens",
                "budget_tokens"}`` dicts for budget-compliance scoring.
            name: Name for this evaluation.
            save_results_path: Path to save results.
            verbose: Enable verbose output.
        """
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        self.trace_events = trace_events or []
        self.agent_order = agent_order or []
        self.budget_ledger = budget_ledger or []

    @staticmethod
    def _event_fields(event: Any):
        """Extract (event_type, agent_name, data) from an event or dict."""
        if hasattr(event, "event_type"):
            event_type = (
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            )
            agent_name = getattr(event, "agent_name", None)
            data = getattr(event, "data", None) or {}
        else:
            event_type = event.get("event_type", "")
            agent_name = event.get("agent_name")
            data = event.get("data", {}) or {}
        return event_type, agent_name, data

    def evaluate_handoff(
        self,
        events: Optional[List[Any]] = None,
        agent_order: Optional[List[str]] = None,
    ) -> List[ContextHandoffResult]:
        """Evaluate context flow between consecutive agents.

        Mirrors the wrapper's token-overlap algorithm: for each adjacent pair
        in ``agent_order``, measures how much of the upstream agent's output
        content appears in the downstream agent's input.
        """
        events = events if events is not None else self.trace_events
        agent_order = agent_order if agent_order is not None else self.agent_order

        if len(agent_order) < 2:
            return []

        agent_outputs: Dict[str, str] = {}
        agent_inputs: Dict[str, str] = {}

        for event in events:
            event_type, agent_name, data = self._event_fields(event)
            if not agent_name:
                continue
            if event_type == "llm_response":
                response = data.get("response_content", "")
                if response:
                    agent_outputs[agent_name] = response
            elif event_type == "llm_request":
                messages = data.get("messages", [])
                if messages:
                    agent_inputs[agent_name] = str(messages)

        results: List[ContextHandoffResult] = []
        for i in range(len(agent_order) - 1):
            from_agent = agent_order[i]
            to_agent = agent_order[i + 1]

            from_output = agent_outputs.get(from_agent, "")
            to_input = agent_inputs.get(to_agent, "")

            content_loss = False
            lost_content = ""

            if from_output and to_input:
                output_tokens = set(re.findall(r"\b[a-zA-Z0-9]{4,}\b", from_output.lower()))
                input_tokens = set(re.findall(r"\b[a-zA-Z0-9]{4,}\b", to_input.lower()))

                exact_match = (
                    from_output in to_input or str(from_output)[:200] in to_input
                )

                if exact_match:
                    context_passed_score = 10.0
                    context_relevance_score = 9.0
                else:
                    overlap = len(output_tokens & input_tokens) / max(len(output_tokens), 1)
                    context_passed_score = min(10.0, overlap * 12 + 2)
                    context_relevance_score = 7.0

                if context_passed_score < 5.0:
                    content_loss = True
                    lost_content = (
                        f"Only {(context_passed_score / 10) * 100:.0f}% of output "
                        "content found in next agent's input"
                    )
            else:
                context_passed_score = 5.0
                context_relevance_score = 5.0

            results.append(
                ContextHandoffResult(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    context_passed_score=context_passed_score,
                    context_relevance_score=context_relevance_score,
                    content_loss_detected=content_loss,
                    lost_content_summary=lost_content,
                    reasoning=f"Context flow from {from_agent} to {to_agent}",
                )
            )

        return results

    def evaluate_budget(
        self,
        ledger: Optional[List[Dict[str, Any]]] = None,
    ) -> List[BudgetComplianceResult]:
        """Evaluate token-budget compliance from a ledger.

        Each ledger entry is a dict with ``agent_name``, ``used_tokens`` and
        ``budget_tokens``. Staying within budget scores 10; exceeding scales
        down by the fraction of overrun.
        """
        ledger = ledger if ledger is not None else self.budget_ledger
        results: List[BudgetComplianceResult] = []

        for entry in ledger:
            agent_name = entry.get("agent_name", "")
            used = int(entry.get("used_tokens", 0) or 0)
            budget = int(entry.get("budget_tokens", 0) or 0)

            if budget <= 0:
                within = True
                score = 5.0
                reasoning = "No budget defined; neutral score"
            elif used <= budget:
                within = True
                score = 10.0
                reasoning = f"Within budget ({used}/{budget} tokens)"
            else:
                within = False
                overrun = (used - budget) / budget
                score = max(1.0, 10.0 - overrun * 10.0)
                reasoning = (
                    f"Exceeded budget by {overrun * 100:.0f}% ({used}/{budget} tokens)"
                )

            results.append(
                BudgetComplianceResult(
                    agent_name=agent_name,
                    used_tokens=used,
                    budget_tokens=budget,
                    within_budget=within,
                    compliance_score=score,
                    reasoning=reasoning,
                )
            )

        return results

    def run(self, print_summary: bool = False, **kwargs) -> ContextEvalResult:
        """Run context evaluation and return an aggregated result.

        Args:
            print_summary: Print a summary table after completion.

        Returns:
            ContextEvalResult with handoff and budget scores.
        """
        self.before_run()

        result = ContextEvalResult(
            handoffs=self.evaluate_handoff(),
            budgets=self.evaluate_budget(),
            eval_id=self.eval_id,
            name=self.name,
        )

        self._result = result
        self.after_run(result)

        if print_summary:
            self._print_summary(result)

        return result

    def _print_summary(self, result: ContextEvalResult) -> None:
        """Print a summary of the context evaluation."""
        print(f"\n{'=' * 60}")
        print(f"ContextEvaluator Results: {result.name}")
        print(f"{'=' * 60}")
        print(f"Overall Score: {result.overall_score:.1f}/10")
        if result.handoffs:
            print(f"Handoff Score: {result.handoff_score:.1f}/10")
            for h in result.handoffs:
                flag = " ⚠️ loss" if h.content_loss_detected else ""
                print(
                    f"  📊 {h.from_agent} → {h.to_agent}: "
                    f"{h.context_passed_score:.1f}/10{flag}"
                )
        if result.budgets:
            print(f"Budget Score: {result.budget_score:.1f}/10")
            for b in result.budgets:
                flag = "" if b.within_budget else " ❌ over"
                print(f"  📊 {b.agent_name}: {b.compliance_score:.1f}/10{flag}")
        print(f"{'=' * 60}\n")
