"""Unit tests for ContextEvaluator (handoff + budget scoring, no live LLM)."""

import pytest

from praisonaiagents.eval import (
    ContextEvaluator,
    ContextEvalResult,
    ContextHandoffResult,
    BudgetComplianceResult,
)


def _make_events(pairs):
    """Build a simple trace from (agent, output, input) tuples."""
    events = []
    for agent, output, input_text in pairs:
        if input_text is not None:
            events.append(
                {
                    "event_type": "llm_request",
                    "agent_name": agent,
                    "data": {"messages": [{"role": "user", "content": input_text}]},
                }
            )
        if output is not None:
            events.append(
                {
                    "event_type": "llm_response",
                    "agent_name": agent,
                    "data": {"response_content": output},
                }
            )
    return events


class TestContextEvaluatorImport:
    def test_importable_from_eval(self):
        from praisonaiagents.eval import ContextEvaluator as CE

        assert CE is ContextEvaluator

    def test_in_dir(self):
        import praisonaiagents.eval as e

        assert "ContextEvaluator" in dir(e)


class TestHandoffScoring:
    def test_no_handoff_with_single_agent(self):
        evaluator = ContextEvaluator(trace_events=[], agent_order=["only"])
        assert evaluator.evaluate_handoff() == []

    def test_perfect_handoff_exact_match(self):
        events = _make_events(
            [
                ("researcher", "The capital of France is Paris.", None),
                ("writer", None, "The capital of France is Paris."),
            ]
        )
        evaluator = ContextEvaluator(
            trace_events=events, agent_order=["researcher", "writer"]
        )
        handoffs = evaluator.evaluate_handoff()
        assert len(handoffs) == 1
        assert handoffs[0].context_passed_score == 10.0
        assert handoffs[0].content_loss_detected is False

    def test_content_loss_detected(self):
        events = _make_events(
            [
                ("researcher", "alpha bravo charlie delta echo foxtrot", None),
                ("writer", None, "totally unrelated words here nothing shared"),
            ]
        )
        evaluator = ContextEvaluator(
            trace_events=events, agent_order=["researcher", "writer"]
        )
        handoffs = evaluator.evaluate_handoff()
        assert handoffs[0].content_loss_detected is True
        assert handoffs[0].context_passed_score < 5.0

    def test_missing_input_neutral_score(self):
        events = _make_events([("researcher", "some output", None)])
        evaluator = ContextEvaluator(
            trace_events=events, agent_order=["researcher", "writer"]
        )
        handoffs = evaluator.evaluate_handoff()
        assert handoffs[0].context_passed_score == 5.0

    def test_supports_object_events(self):
        class Ev:
            def __init__(self, event_type, agent_name, data):
                self.event_type = event_type
                self.agent_name = agent_name
                self.data = data

        events = [
            Ev("llm_response", "a", {"response_content": "shared token here today"}),
            Ev("llm_request", "b", {"messages": ["shared token here today"]}),
        ]
        evaluator = ContextEvaluator(trace_events=events, agent_order=["a", "b"])
        handoffs = evaluator.evaluate_handoff()
        assert handoffs[0].context_passed_score == 10.0


class TestBudgetScoring:
    def test_within_budget(self):
        evaluator = ContextEvaluator(
            budget_ledger=[
                {"agent_name": "a", "used_tokens": 100, "budget_tokens": 200}
            ]
        )
        budgets = evaluator.evaluate_budget()
        assert budgets[0].within_budget is True
        assert budgets[0].compliance_score == 10.0

    def test_over_budget(self):
        evaluator = ContextEvaluator(
            budget_ledger=[
                {"agent_name": "a", "used_tokens": 300, "budget_tokens": 100}
            ]
        )
        budgets = evaluator.evaluate_budget()
        assert budgets[0].within_budget is False
        assert budgets[0].compliance_score < 10.0
        assert budgets[0].compliance_score >= 1.0

    def test_no_budget_neutral(self):
        evaluator = ContextEvaluator(
            budget_ledger=[{"agent_name": "a", "used_tokens": 50, "budget_tokens": 0}]
        )
        budgets = evaluator.evaluate_budget()
        assert budgets[0].compliance_score == 5.0


class TestRun:
    def test_run_returns_result(self):
        events = _make_events(
            [
                ("a", "shared token here today", None),
                ("b", None, "shared token here today"),
            ]
        )
        evaluator = ContextEvaluator(
            trace_events=events,
            agent_order=["a", "b"],
            budget_ledger=[{"agent_name": "a", "used_tokens": 10, "budget_tokens": 20}],
        )
        result = evaluator.run(print_summary=False)
        assert isinstance(result, ContextEvalResult)
        assert result.handoff_score == 10.0
        assert result.budget_score == 10.0
        assert result.overall_score == 10.0
        assert result.content_loss_detected is False

    def test_result_to_dict_has_context_score_fields(self):
        evaluator = ContextEvaluator(
            budget_ledger=[{"agent_name": "a", "used_tokens": 10, "budget_tokens": 20}]
        )
        d = evaluator.run(print_summary=False).to_dict()
        assert "overall_score" in d
        assert "handoff_score" in d
        assert "budget_score" in d

    def test_empty_evaluator_zero_score(self):
        result = ContextEvaluator().run(print_summary=False)
        assert result.overall_score == 0.0


class TestEvalSuiteIntegration:
    def test_composes_into_suite(self):
        from praisonaiagents.eval import EvalSuite

        events = _make_events(
            [
                ("a", "shared token here today", None),
                ("b", None, "shared token here today"),
            ]
        )
        suite = EvalSuite(
            evaluators=[ContextEvaluator(trace_events=events, agent_order=["a", "b"])]
        )
        result = suite.run(print_summary=False)
        assert result.overall_score == 10.0
