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
