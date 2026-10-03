from __future__ import annotations

from unittest import mock

import pytest

from praisonaiagents.decisions.routing import (
    DecisionRoutePlan,
    DecisionTriageRouter,
    triaged_start,
)


def test_triaged_start_delegates_by_choice():
    fake_decision = mock.Mock()
    fake_decision.choice.return_value = "billing"
    fake_decision.confidence.return_value = 0.95
    fake_decision.answers = {}

    class FakeAgent:
        def __init__(self):
            self.prompt = None

        def start(self, prompt, **kwargs):
            self.prompt = prompt
            return "BILLING-OK"

    billing = FakeAgent()
    plan = DecisionRoutePlan(
        route_question="team",
        questions={"team": {"type": "choice", "instructions": "x", "criteria": {"billing": "b"}}},
        routes={"billing": billing, "technical": FakeAgent()},
    )

    with mock.patch("praisonaiagents.decisions.routing.triage_decision", return_value=fake_decision):
        out = triaged_start("refund please", plan)

    assert out["route"] == "billing"
    assert out["response"] == "BILLING-OK"
    assert billing.prompt == "refund please"


def test_decision_triage_router():
    router = DecisionTriageRouter(
        DecisionRoutePlan(
            questions={"team": {"type": "choice", "instructions": "x", "criteria": {"other": "o"}}},
            routes={"other": lambda d: "OK"},
        )
    )
    fake = mock.Mock(choice=lambda k: "other", confidence=lambda k: 1.0, answers={}, model="nimble", raw={})
    with mock.patch("praisonaiagents.decisions.routing.triage_decision", return_value=fake):
        out = router.start("hello")
    assert out["response"] == "OK"


def _choice_q(*criteria):
    return {"type": "choice", "instructions": "x", "criteria": {c: c for c in criteria}}


def test_plan_rejects_empty_questions():
    with pytest.raises(ValueError):
        DecisionRoutePlan(questions={}, routes={"a": lambda d: "x"})


def test_plan_rejects_non_choice_route_question():
    with pytest.raises(ValueError):
        DecisionRoutePlan(
            route_question="refund",
            questions={"refund": {"type": "noul", "instructions": "x"}},
            routes={"a": lambda d: "x"},
        )


def test_missing_confidence_triggers_fallback():
    fake = mock.Mock()
    fake.choice.return_value = "billing"
    fake.confidence.return_value = None
    fake.answers = {}
    plan = DecisionRoutePlan(
        route_question="team",
        min_confidence=0.5,
        questions={"team": _choice_q("billing", "other")},
        routes={"billing": lambda d: "B", "other": lambda d: "FALLBACK"},
        fallback_route="other",
    )
    with mock.patch("praisonaiagents.decisions.routing.triage_decision", return_value=fake):
        out = triaged_start("hi", plan)
    assert out["route"] == "other"


def test_extra_state_does_not_clobber_prompt():
    from praisonaiagents.decisions.routing import triage_decision

    captured = {}

    def fake_system_one(*, state, questions, model, api_base):
        captured["state"] = dict(state)
        return mock.Mock()

    with mock.patch("praisonaiagents.decisions.routing.system_one", fake_system_one):
        triage_decision(
            "classify-me",
            questions={"team": _choice_q("a")},
            state_key="message",
            extra_state={"message": "SHOULD-NOT-WIN", "locale": "en"},
        )
    assert captured["state"]["message"] == "classify-me"
    assert captured["state"]["locale"] == "en"
