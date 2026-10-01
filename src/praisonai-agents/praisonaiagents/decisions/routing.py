"""Route user input through System One decision models before chat agents."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Protocol, Union

from .system_one import (
    SystemOneResult,
    choice_question,
    system_one,
)


class AgentLike(Protocol):
    def start(self, prompt: str, **kwargs: Any) -> Any: ...


RouteTarget = Union[AgentLike, str, Callable[[SystemOneResult], Any]]


@dataclass
class DecisionRoutePlan:
    """Configuration for decision-first routing."""

    route_question: str = "team"
    decision_model: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_DECISION_MODEL", "nimble")
    )
    api_base: Optional[str] = None
    state_key: str = "message"
    min_confidence: Optional[float] = None
    questions: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    routes: Mapping[str, RouteTarget] = field(default_factory=dict)
    fallback_route: Optional[str] = None

    def __post_init__(self) -> None:
        if self.route_question not in self.questions and self.questions:
            raise ValueError(
                f"route_question {self.route_question!r} missing from questions keys "
                f"{list(self.questions.keys())}"
            )


def default_ticket_triage_questions() -> dict[str, dict[str, Any]]:
    """Preset for support ticket routing (Ollama blog example)."""
    return {
        "team": choice_question(
            "Which team should handle this ticket?",
            {
                "billing": "Payments and refunds",
                "technical": "Bugs and integrations",
                "other": "None of the above",
            },
        ),
        "refund": {
            "type": "noul",
            "instructions": "Does the customer explicitly ask for a refund?",
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this ticket?",
            "criteria": ["Routine", "Soon", "Urgent"],
        },
    }


def triage_decision(
    message: str,
    *,
    questions: Mapping[str, Mapping[str, Any]],
    decision_model: str = "nimble",
    api_base: Optional[str] = None,
    state_key: str = "message",
    extra_state: Optional[Mapping[str, Any]] = None,
) -> SystemOneResult:
    """Run System One on *message* without invoking a chat LLM."""
    state = {state_key: message}
    if extra_state:
        state.update(dict(extra_state))
    return system_one(
        state=state,
        questions=questions,
        model=decision_model,
        api_base=api_base,
    )


def resolve_route_key(result: SystemOneResult, route_question: str) -> Optional[str]:
    return result.choice(route_question)


def _invoke_target(target: RouteTarget, prompt: str, decision: SystemOneResult) -> Any:
    if isinstance(target, str):
        from praisonaiagents import Agent

        return Agent(instructions="You are a helpful assistant.", llm=target).start(prompt)
    if callable(target):
        return target(decision)
    return target.start(prompt)


def triaged_start(
    prompt: str,
    plan: DecisionRoutePlan,
    *,
    extra_state: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """
    Triage with a decision model, then delegate to the mapped chat agent/model.

    Returns a dict with ``decision``, ``route``, ``confidence``, and ``response``.
    """
    decision = triage_decision(
        prompt,
        questions=plan.questions,
        decision_model=plan.decision_model,
        api_base=plan.api_base,
        state_key=plan.state_key,
        extra_state=extra_state,
    )
    route_key = resolve_route_key(decision, plan.route_question)
    conf = decision.confidence(plan.route_question)
    if plan.min_confidence is not None and conf is not None and conf < plan.min_confidence:
        route_key = plan.fallback_route or route_key
    if not route_key or route_key not in plan.routes:
        route_key = plan.fallback_route or next(iter(plan.routes), None)
    if not route_key or route_key not in plan.routes:
        raise RuntimeError(
            f"No route for decision choice {route_key!r}; "
            f"available routes: {list(plan.routes.keys())}"
        )
    target = plan.routes[route_key]
    response = _invoke_target(target, prompt, decision)
    return {
        "decision": decision,
        "route": route_key,
        "confidence": conf,
        "response": response,
    }


class DecisionTriageRouter:
    """Object-oriented wrapper for repeated triage + chat routing."""

    def __init__(self, plan: DecisionRoutePlan):
        self.plan = plan

    def decide(self, message: str, **extra_state: Any) -> SystemOneResult:
        return triage_decision(
            message,
            questions=self.plan.questions,
            decision_model=self.plan.decision_model,
            api_base=self.plan.api_base,
            state_key=self.plan.state_key,
            extra_state=extra_state or None,
        )

    def start(self, prompt: str, **extra_state: Any) -> dict[str, Any]:
        return triaged_start(prompt, self.plan, extra_state=extra_state or None)
