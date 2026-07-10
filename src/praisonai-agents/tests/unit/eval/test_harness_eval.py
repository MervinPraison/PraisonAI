"""Unit tests for eval/harness_eval.py — HarnessEvaluator + CSV adapter."""
import pytest

from praisonaiagents.eval import (
    HarnessEvaluator,
    HarnessResult,
    harness_row_to_eval_case,
    EvalCase,
    EvalResult,
    EvalReport,
)
from praisonaiagents.eval.harness_eval import _schema_hash


class TestHarnessImports:
    """HarnessEvaluator must be importable from praisonaiagents.eval."""

    def test_public_imports(self):
        assert HarnessEvaluator is not None
        assert HarnessResult is not None
        assert callable(harness_row_to_eval_case)


class TestHarnessRowToEvalCase:
    """CSV row -> EvalCase adapter."""

    def test_basic_mapping(self):
        row = {"id": "s1", "prompt": "list files", "fixture": "repo", "rubric": "clean output"}
        case = harness_row_to_eval_case(row)
        assert isinstance(case, EvalCase)
        assert case.name == "s1"
        assert case.input == "list files"
        assert case.metadata["fixture"] == "repo"
        assert case.metadata["rubric"] == "clean output"
        assert case.metadata["source"] == "harness"
        assert case.criteria == ["clean output"]

    def test_alternate_column_names(self):
        row = {"name": "alt", "input": "do thing"}
        case = harness_row_to_eval_case(row)
        assert case.name == "alt"
        assert case.input == "do thing"

    def test_missing_optional_fields(self):
        row = {"id": "s2", "prompt": "hello"}
        case = harness_row_to_eval_case(row)
        assert "fixture" not in case.metadata
        assert case.criteria == []


class TestHarnessEvaluator:
    """HarnessEvaluator scoring behaviour."""

    def test_all_pass(self):
        trace = {
            "tool_calls": [{"name": "read_file"}, {"name": "write_file"}],
            "artifacts": ["out.txt"],
            "tool_schema": {"read_file": {}, "write_file": {}},
            "judge_score": 9.0,
        }
        ev = HarnessEvaluator(
            trace=trace,
            required_artifacts=["out.txt"],
            min_tool_calls=1,
            name="ok",
        )
        result = ev.run()
        assert isinstance(result, HarnessResult)
        assert result.passed is True
        assert result.score == 1.0
        assert result.tool_call_count == 2
        assert result.artifacts_complete is True

    def test_missing_artifact_fails(self):
        trace = {"tool_calls": [1], "artifacts": []}
        ev = HarnessEvaluator(trace=trace, required_artifacts=["result.json"])
        result = ev.run()
        assert result.passed is False
        assert result.artifacts_complete is False
        assert "result.json" in result.missing_artifacts

    def test_min_tool_calls_gate(self):
        trace = {"tool_calls": [], "artifacts": []}
        ev = HarnessEvaluator(trace=trace, min_tool_calls=2)
        result = ev.run()
        assert result.passed is False

    def test_int_tool_calls_supported(self):
        trace = {"tool_calls": 3, "artifacts": []}
        ev = HarnessEvaluator(trace=trace, min_tool_calls=2)
        result = ev.run()
        assert result.tool_call_count == 3
        assert result.passed is True

    def test_schema_hash_parity(self):
        schema = {"tool_a": {"args": ["x"]}}
        expected = _schema_hash(schema)
        good = HarnessEvaluator(trace={"tool_schema": schema}, expected_schema_hash=expected)
        assert good.run().schema_consistent is True

        bad = HarnessEvaluator(
            trace={"tool_schema": {"tool_b": {}}},
            expected_schema_hash=expected,
        )
        bad_result = bad.run()
        assert bad_result.schema_consistent is False
        assert bad_result.passed is False

    def test_judge_threshold(self):
        low = HarnessEvaluator(trace={"judge_score": 4.0}, judge_threshold=7.0)
        low_result = low.run()
        assert low_result.judge_passed is False
        assert low_result.passed is False

    def test_no_judge_is_not_a_gate(self):
        ev = HarnessEvaluator(trace={"tool_calls": [1], "artifacts": []})
        result = ev.run()
        assert result.judge_passed is True
        assert result.judge_score is None

    def test_to_eval_result(self):
        trace = {"tool_calls": [1], "artifacts": ["a.txt"], "judge_score": 8.0}
        ev = HarnessEvaluator(trace=trace, required_artifacts=["a.txt"], name="case1")
        eval_result = ev.to_eval_result()
        assert isinstance(eval_result, EvalResult)
        assert eval_result.case_name == "case1"
        assert eval_result.passed is True
        assert "artifacts_complete" in eval_result.criteria_scores


class TestHarnessEvalReportExport:
    """Harness results aggregate into an EvalReport-compatible structure."""

    def test_csv_rows_to_report(self):
        rows = [
            {"id": "s1", "prompt": "p1", "fixture": "f1"},
            {"id": "s2", "prompt": "p2", "fixture": "f2"},
        ]
        traces = {
            "s1": {"tool_calls": [1], "artifacts": ["s1.txt"]},
            "s2": {"tool_calls": [], "artifacts": []},
        }

        results = []
        for row in rows:
            case = harness_row_to_eval_case(row)
            required = [f"{case.name}.txt"]
            ev = HarnessEvaluator(
                trace=traces[case.name],
                required_artifacts=required,
                name=case.name,
            )
            ev.run()
            results.append(ev.to_eval_result(case_name=case.name))

        passed = sum(1 for r in results if r.passed)
        report = EvalReport(
            package_name="harness_smoke",
            total_cases=len(results),
            passed_cases=passed,
            failed_cases=len(results) - passed,
            average_score=sum(r.score for r in results) / len(results),
            results=results,
        )

        assert report.total_cases == 2
        assert report.passed_cases == 1
        assert report.failed_cases == 1
        assert report.all_passed is False
        d = report.to_dict()
        assert d["package_name"] == "harness_smoke"
        assert len(d["results"]) == 2


class TestHarnessInEvalSuite:
    """HarnessEvaluator runs inside EvalSuite alongside other evaluators."""

    def test_suite_includes_harness(self):
        from praisonaiagents.eval import EvalSuite

        harness = HarnessEvaluator(
            trace={"tool_calls": [1], "artifacts": ["x.txt"]},
            required_artifacts=["x.txt"],
            name="harness_smoke",
        )
        suite = EvalSuite(evaluators=[harness], name="mixed")
        result = suite.run(print_summary=False)
        assert result.success is True
        assert len(result.evaluator_results) == 1
