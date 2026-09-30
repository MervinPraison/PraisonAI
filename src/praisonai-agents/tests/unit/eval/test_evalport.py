"""Unit tests for eval/evalport.py - EvalPort framework-neutral adapter.

Covers the dependency-free round-trip between PraisonAI eval models and the
EvalPort spec dicts. A real agentic test (gated by RUN_LIVE_TESTS=1) runs a live
Agent and exports its EvalReport as an EvalPort ResultSet.
"""
import json
import os
import re
from datetime import datetime

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
from praisonaiagents.eval.evalport import EVALPORT_SPEC_VERSION, VERDICT_GRADER_ID


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
        assert suite["version"] == EVALPORT_SPEC_VERSION
        assert suite["id"] == "support_agent_eval"
        assert suite["name"] == "support_agent_eval"
        assert suite["description"] == "Support agent suite"
        native = suite["metadata"]["praisonai"]
        assert native == {"version": "2.1.0", "thresholds": {"accuracy": 0.9}, "seed": 7}

        grader_ids = [g["id"] for g in suite["graders"]]
        assert grader_ids == [VERDICT_GRADER_ID, "answer_correct"]
        for g in suite["graders"]:
            assert g["type"] == "custom" and g["params"]["handler"]

        case = suite["test_cases"][0]
        assert case["id"] == "refund_policy"
        assert case["input"] == "What's your refund policy?"
        assert case["expected_output"] == "30 days, unused, receipt required"
        assert case["graders"] == ["answer_correct"]
        assert case["metadata"]["tier"] == "gold"
        assert case["timeout_ms"] == 15000
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
        case = to_evalport(pkg)["test_cases"][0]
        assert "expected_output" not in case
        # EvalPort requires >= 1 grader per test case: fall back to the verdict grader.
        assert case["graders"] == [VERDICT_GRADER_ID]
        assert from_evalport(to_evalport(pkg)).cases[0].criteria == []

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
        case = to_evalport(pkg)["test_cases"][0]
        assert case["timeout_ms"] == 15000
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

    def test_external_spec_suite_imports(self):
        """A spec-shaped suite from another tool (test_cases, inline graders)."""
        external = {
            "version": "1.0.0",
            "id": "hub_suite",
            "test_cases": [
                {
                    "id": "c1",
                    "input": "hi",
                    "graders": [{"id": "has_hi", "type": "contains", "params": {"substring": "hi"}}],
                    "timeout_ms": 2500,
                }
            ],
        }
        pkg = from_evalport(external)
        assert pkg.name == "hub_suite"
        assert pkg.version == "1.0.0"  # spec version is not the package version
        assert pkg.cases[0].criteria == ["has_hi"]
        assert pkg.cases[0].timeout_seconds == 2.5

    def test_legacy_suite_still_imports(self):
        """Suites emitted by the pre-spec-alignment adapter still import."""
        legacy = {
            "evalport_version": "1.0",
            "kind": "suite",
            "name": "old",
            "version": "3.0.0",
            "cases": [{"id": "c1", "input": "hi", "timeout_seconds": 5.0}],
            "thresholds": {"accuracy": 0.8},
            "seed": 1,
        }
        pkg = from_evalport(legacy)
        assert pkg.version == "3.0.0"
        assert pkg.thresholds == {"accuracy": 0.8}
        assert pkg.seed == 1
        assert pkg.cases[0].timeout_seconds == 5.0


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
        rs = report_to_evalport(
            self._report(), run_id="run-1", started_at="2026-09-29T00:00:00+00:00"
        )
        assert rs["version"] == EVALPORT_SPEC_VERSION
        assert rs["suite_id"] == "support_agent_eval"
        assert rs["run_id"] == "run-1"
        assert rs["started_at"] == "2026-09-29T00:00:00+00:00"
        assert rs["runner"]["name"] == "praisonaiagents"
        assert rs["summary"]["total"] == 2
        assert rs["summary"]["passed"] == 1
        assert rs["summary"]["failed"] == 1
        assert rs["summary"]["pass_rate"] == 0.5
        assert rs["summary"]["avg_score"] == 0.6
        assert rs["metadata"]["praisonai"]["thresholds_met"] == {"accuracy": False}
        assert len(rs["results"]) == 2

    def test_run_id_and_started_at_defaults(self):
        rs = report_to_evalport(self._report())
        assert isinstance(rs["run_id"], str) and rs["run_id"]
        assert datetime.fromisoformat(rs["started_at"]).tzinfo is not None
        assert report_to_evalport(self._report())["run_id"] != rs["run_id"]

    def test_per_case_fields(self):
        rs = report_to_evalport(self._report())
        passed, failed = rs["results"]
        assert passed["test_case_id"] == "refund_policy"
        assert passed["passed"] is True
        assert passed["grader_results"] == [
            {"grader_id": VERDICT_GRADER_ID, "type": "custom", "score": 0.95, "passed": True}
        ]
        assert passed["duration_ms"] == 120
        assert passed["actual_output"] == "30 days."
        assert passed["metadata"]["praisonai"]["criteria_scores"] == {"answer_correct": 0.95}
        assert "error" not in passed

        assert failed["test_case_id"] == "shipping"
        assert failed["passed"] is False
        assert failed["grader_results"][0]["score"] == 0.25
        assert failed["grader_results"][0]["passed"] is False
        assert failed["error"] == {"type": "runner_error", "message": "timeout"}
        assert "actual_output" not in failed
        assert "metadata" not in failed

    def test_out_of_range_score_is_clamped_with_raw_kept(self):
        report = EvalReport(
            package_name="p", total_cases=1, passed_cases=1, failed_cases=0,
            average_score=7.5,
            results=[EvalResult(case_name="c", passed=True, score=7.5)],
        )
        rs = report_to_evalport(report)
        gr = rs["results"][0]["grader_results"][0]
        assert gr["score"] == 1.0
        assert gr["metadata"] == {"openeval.raw_score": 7.5}
        assert rs["summary"]["avg_score"] == 1.0
        assert rs["metadata"]["praisonai"]["average_score"] == 7.5


def _structural_suite_errors(suite):
    """Minimal EvalPort Suite checks that need no third-party packages."""
    errs = []
    if not re.match(r"^\d+\.\d+\.\d+(?:[-+].+)?$", suite.get("version", "")):
        errs.append("version")
    if not suite.get("id"):
        errs.append("id")
    allowed = {"$schema", "version", "id", "name", "description", "graders",
               "test_cases", "test_cases_file", "config", "metadata", "tags"}
    errs += [f"extra:{k}" for k in set(suite) - allowed]
    grader_ids = [g["id"] for g in suite.get("graders", [])]
    if len(grader_ids) != len(set(grader_ids)):
        errs.append("duplicate grader id")
    if not suite.get("test_cases"):
        errs.append("test_cases")
    for tc in suite.get("test_cases", []):
        if not tc.get("id") or not tc.get("input") or not tc.get("graders"):
            errs.append(f"test_case:{tc.get('id')}")
        errs += [f"dangling:{g}" for g in tc.get("graders", [])
                 if isinstance(g, str) and g not in grader_ids]
    return errs


def _structural_result_set_errors(rs):
    """Minimal EvalPort ResultSet checks that need no third-party packages."""
    errs = []
    if not re.match(r"^\d+\.\d+\.\d+(?:[-+].+)?$", rs.get("version", "")):
        errs.append("version")
    errs += [k for k in ("suite_id", "run_id", "started_at") if not rs.get(k)]
    allowed = {"$schema", "version", "suite_id", "suite_version", "run_id", "started_at",
               "completed_at", "provider", "runner", "isolation", "group", "results",
               "summary", "metadata"}
    errs += [f"extra:{k}" for k in set(rs) - allowed]
    item_keys = {"test_case_id", "actual_output", "attempt", "completed_at",
                 "grader_results", "passed", "duration_ms", "error", "metadata"}
    for r in rs.get("results", []):
        errs += [f"result extra:{k}" for k in set(r) - item_keys]
        if not r.get("test_case_id") or not isinstance(r.get("passed"), bool):
            errs.append("result")
        if not isinstance(r.get("duration_ms", 0), int):
            errs.append("duration_ms")
        for g in r.get("grader_results", None) or [None]:
            if not g or not g.get("grader_id") or not isinstance(g.get("passed"), bool):
                errs.append("grader_result")
            elif g["score"] is not None and not 0 <= g["score"] <= 1:
                errs.append("grader_result score")
    return errs


class TestEvalPortSpecConformance:
    """Emitted documents must pass the EvalPort validators."""

    def _docs(self):
        pkg = TestSuiteConversion()._pkg()
        pkg.add_case(EvalCase(name="no_criteria", input="hello"))
        return to_evalport(pkg), report_to_evalport(TestResultSetConversion()._report())

    def test_structurally_valid_without_sdk(self):
        suite, rs = self._docs()
        assert _structural_suite_errors(suite) == []
        assert _structural_result_set_errors(rs) == []
        json.dumps(suite)
        json.dumps(rs)

    def test_valid_with_evalport_sdk(self):
        validate = pytest.importorskip("openeval.validate")
        suite, rs = self._docs()
        suite_result = validate.validate_suite(suite)
        assert suite_result.valid, suite_result.errors
        rs_result = validate.validate_result_set(rs)
        assert rs_result.valid, rs_result.errors


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
        assert result_set["suite_id"] == "math_eval"
        assert result_set["results"][0]["test_case_id"] == "math_addition"
        assert result_set["results"][0]["actual_output"] == str(answer)
        assert _structural_result_set_errors(result_set) == []
