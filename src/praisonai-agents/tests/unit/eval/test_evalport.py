"""Unit tests for eval/evalport.py - EvalPort framework-neutral adapter.

Covers the dependency-free round-trip between PraisonAI eval models and the
EvalPort spec dicts. A real agentic test (gated by RUN_LIVE_TESTS=1) runs a live
Agent and exports its EvalReport as an EvalPort ResultSet.
"""
import os

import pytest

from praisonaiagents.eval import (
    EvalCase,
    EvalPackage,
    EvalReport,
    EvalResult,
    from_evalport,
    report_to_evalport,
    to_evalport,
)


class TestEvalPortImports:
    """Adapter functions must be importable from praisonaiagents.eval."""

    def test_public_imports(self):
        assert callable(to_evalport)
        assert callable(from_evalport)
        assert callable(report_to_evalport)


class TestSuiteConversion:
    """EvalPackage <-> EvalPort Suite."""

    def _pkg(self):
        return EvalPackage(
            name="support_agent_eval",
            description="Support agent suite",
            version="2.1.0",
            cases=[
                EvalCase(
                    name="refund_policy",
                    input="What's your refund policy?",
                    expected="30 days, unused, receipt required",
                    criteria=["answer_correct"],
                    metadata={"tier": "gold"},
                    timeout_seconds=15.0,
                )
            ],
            thresholds={"accuracy": 0.9},
            seed=7,
        )

    def test_to_evalport_shape(self):
        suite = to_evalport(self._pkg())
        assert suite["kind"] == "suite"
        assert suite["name"] == "support_agent_eval"
        assert suite["version"] == "2.1.0"
        assert suite["thresholds"] == {"accuracy": 0.9}
        assert suite["seed"] == 7
        assert "evalport_version" in suite

        case = suite["cases"][0]
        assert case["id"] == "refund_policy"
        assert case["input"] == "What's your refund policy?"
        assert case["expected_output"] == "30 days, unused, receipt required"
        assert case["graders"] == ["answer_correct"]
        assert case["metadata"]["tier"] == "gold"
        assert case["timeout_seconds"] == 15.0
        assert "timeout_seconds" not in case["metadata"]

    def test_from_evalport_shape(self):
        suite = to_evalport(self._pkg())
        pkg = from_evalport(suite)
        assert isinstance(pkg, EvalPackage)
        assert pkg.name == "support_agent_eval"
        assert pkg.version == "2.1.0"
        assert pkg.thresholds == {"accuracy": 0.9}
        assert pkg.seed == 7

        case = pkg.cases[0]
        assert isinstance(case, EvalCase)
        assert case.name == "refund_policy"
        assert case.input == "What's your refund policy?"
        assert case.expected == "30 days, unused, receipt required"
        assert case.criteria == ["answer_correct"]
        assert case.metadata["tier"] == "gold"
        assert case.timeout_seconds == 15.0

    def test_round_trip_preserves_dict(self):
        pkg = self._pkg()
        round_tripped = from_evalport(to_evalport(pkg))
        assert round_tripped.to_dict() == pkg.to_dict()

    def test_external_suite_minimal_fields(self):
        """A suite from another tool with only required fields still imports."""
        external = {
            "name": "hub_suite",
            "cases": [{"id": "c1", "input": "hi"}],
        }
        pkg = from_evalport(external)
        assert pkg.name == "hub_suite"
        assert len(pkg.cases) == 1
        assert pkg.cases[0].name == "c1"
        assert pkg.cases[0].input == "hi"
        assert pkg.cases[0].expected is None

    def test_case_without_expected_or_criteria(self):
        pkg = EvalPackage(name="p", cases=[EvalCase(name="c", input="x")])
        case = to_evalport(pkg)["cases"][0]
        assert "expected_output" not in case
        assert "graders" not in case

    def test_metadata_timeout_key_does_not_corrupt_native_timeout(self):
        """A user ``metadata['timeout_seconds']`` must not clobber the native one."""
        pkg = EvalPackage(
            name="p",
            cases=[
                EvalCase(
                    name="c",
                    input="x",
                    metadata={"timeout_seconds": 999},
                    timeout_seconds=15.0,
                )
            ],
        )
        case = to_evalport(pkg)["cases"][0]
        assert case["timeout_seconds"] == 15.0
        assert case["metadata"]["timeout_seconds"] == 999

        round_tripped = from_evalport(to_evalport(pkg)).cases[0]
        assert round_tripped.timeout_seconds == 15.0
        assert round_tripped.metadata["timeout_seconds"] == 999

    def test_external_suite_metadata_timeout_fallback(self):
        """External suites that only put timeout in metadata still import it."""
        external = {
            "name": "hub",
            "cases": [{"id": "c1", "input": "hi", "metadata": {"timeout_seconds": 45}}],
        }
        case = from_evalport(external).cases[0]
        assert case.timeout_seconds == 45
        assert case.metadata["timeout_seconds"] == 45


class TestResultSetConversion:
    """EvalReport -> EvalPort ResultSet."""

    def _report(self):
        return EvalReport(
            package_name="support_agent_eval",
            total_cases=2,
            passed_cases=1,
            failed_cases=1,
            average_score=0.6,
            thresholds_met={"accuracy": False},
            results=[
                EvalResult(
                    case_name="refund_policy",
                    passed=True,
                    score=0.95,
                    actual_output="30 days.",
                    latency_ms=120.0,
                    criteria_scores={"answer_correct": 0.95},
                ),
                EvalResult(
                    case_name="shipping",
                    passed=False,
                    score=0.25,
                    error="timeout",
                    latency_ms=300.0,
                ),
            ],
        )

    def test_result_set_shape(self):
        rs = report_to_evalport(self._report())
        assert rs["kind"] == "result_set"
        assert rs["suite_name"] == "support_agent_eval"
        assert rs["summary"]["total"] == 2
        assert rs["summary"]["passed"] == 1
        assert rs["summary"]["failed"] == 1
        assert rs["summary"]["pass_rate"] == 0.5
        assert rs["summary"]["average_score"] == 0.6
        assert rs["summary"]["thresholds_met"] == {"accuracy": False}
        assert len(rs["results"]) == 2

    def test_per_case_fields(self):
        rs = report_to_evalport(self._report())
        passed, failed = rs["results"]
        assert passed["case_id"] == "refund_policy"
        assert passed["passed"] is True
        assert passed["score"] == 0.95
        assert passed["latency_ms"] == 120.0
        assert passed["actual_output"] == "30 days."
        assert passed["grader_scores"] == {"answer_correct": 0.95}
        assert "error" not in passed

        assert failed["case_id"] == "shipping"
        assert failed["passed"] is False
        assert failed["error"] == "timeout"
        assert "actual_output" not in failed
        assert "grader_scores" not in failed


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1",
    reason="Real agentic test requires RUN_LIVE_TESTS=1 and an API key",
)
class TestEvalPortRealAgent:
    """Real agentic test: run a live Agent, export the report as EvalPort."""

    def test_agent_report_exports_to_evalport(self):
        from praisonaiagents import Agent
        from praisonaiagents.eval import HarnessEvaluator

        agent = Agent(
            name="math",
            instructions="You answer math questions with only the number.",
        )
        answer = agent.start("What is 2 + 2?")
        assert answer is not None

        trace = {
            "tool_calls": [],
            "artifacts": [],
            "judge_score": 10.0 if "4" in str(answer) else 0.0,
        }
        result = HarnessEvaluator(trace=trace, name="math_addition").run()

        report = EvalReport(
            package_name="math_eval",
            total_cases=1,
            passed_cases=1 if result.passed else 0,
            failed_cases=0 if result.passed else 1,
            average_score=result.score,
            results=[
                EvalResult(
                    case_name="math_addition",
                    passed=result.passed,
                    score=result.score,
                    actual_output=str(answer),
                )
            ],
        )

        result_set = report_to_evalport(report)
        assert result_set["kind"] == "result_set"
        assert result_set["suite_name"] == "math_eval"
        assert result_set["results"][0]["case_id"] == "math_addition"
        assert result_set["results"][0]["actual_output"] == str(answer)
