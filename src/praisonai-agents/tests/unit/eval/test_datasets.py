"""Eval task sets load from JSONL, and passing runs export as training data.

EvalCase.from_dict existed but nothing read a FILE, so a task set had to be
assembled in Python. And praisonai-train sat in the repo with no connection to
eval -- no way to turn the runs that scored well into fine-tuning data.
"""
import json
import pytest

from praisonaiagents.eval.datasets import (
    DatasetError,
    export_sft,
    iter_jsonl,
    load_cases,
    sft_records,
)
from praisonaiagents.eval.package import EvalResult


def _jsonl(tmp_path, *rows):
    path = tmp_path / "tasks.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(path)


class _Report:
    def __init__(self, results):
        self.results = results


def _result(name, passed, score, output="4", prompt="2+2?"):
    return EvalResult(case_name=name, passed=passed, score=score,
                      actual_output=output, record={"input": prompt})


class TestLoading:
    def test_cases_load_from_a_file(self, tmp_path):
        path = _jsonl(tmp_path, {"name": "add", "input": "2+2?", "expected": "4"})
        cases = load_cases(path)
        assert (cases[0].name, cases[0].input, cases[0].expected) == ("add", "2+2?", "4")

    def test_common_column_aliases_are_accepted(self, tmp_path):
        """A task set exported from another tool is the normal case."""
        path = _jsonl(tmp_path, {"prompt": "capital?", "answer": "Paris"})
        case = load_cases(path)[0]
        assert case.input == "capital?"
        assert case.expected == "Paris"

    def test_unrecognised_columns_are_kept_as_metadata(self, tmp_path):
        """Datasets carry provenance worth having in the report."""
        path = _jsonl(tmp_path, {"input": "q", "difficulty": "easy", "source": "sheet1"})
        assert load_cases(path)[0].metadata == {"difficulty": "easy", "source": "sheet1"}

    def test_blank_lines_and_comments_are_skipped(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text('\n// a comment\n{"input": "q"}\n\n', encoding="utf-8")
        assert len(load_cases(str(path))) == 1


class TestLoadingRefusals:
    def test_a_missing_file_is_named(self, tmp_path):
        with pytest.raises(DatasetError, match="No such dataset file"):
            load_cases(str(tmp_path / "nope.jsonl"))

    def test_a_bad_line_is_reported_by_number(self, tmp_path):
        """'invalid JSON' is not actionable on a thousand-line dataset."""
        path = tmp_path / "t.jsonl"
        path.write_text('{"input": "ok"}\nnot json\n', encoding="utf-8")
        with pytest.raises(DatasetError, match=r":2:"):
            load_cases(str(path))

    def test_error_reports_physical_line_past_skipped_lines(self, tmp_path):
        """Blank/comment lines must not shift the reported file:line."""
        path = tmp_path / "t.jsonl"
        # Data row is on physical line 4; a naive row-counter would say line 2.
        path.write_text('\n// comment\n\n{"expected": "no input here"}\n', encoding="utf-8")
        with pytest.raises(DatasetError, match=r":4:"):
            load_cases(str(path))

    def test_a_non_object_line_is_refused(self, tmp_path):
        path = tmp_path / "t.jsonl"
        path.write_text('[1, 2, 3]\n', encoding="utf-8")
        with pytest.raises(DatasetError, match="must be a JSON object"):
            load_cases(str(path))

    def test_an_empty_file_is_refused(self, tmp_path):
        """An empty task set would report a perfect pass rate over nothing."""
        path = tmp_path / "t.jsonl"
        path.write_text("\n", encoding="utf-8")
        with pytest.raises(DatasetError, match="no cases"):
            load_cases(str(path))


class TestSFTExport:
    def test_only_passing_runs_are_exported(self, tmp_path):
        """Training on a rejected run teaches the behaviour the eval catches."""
        report = _Report([_result("a", True, 1.0), _result("b", False, 0.2)])
        out = tmp_path / "train.jsonl"
        assert export_sft(report, str(out)) == 1

    def test_min_score_filters_weak_passes(self, tmp_path):
        report = _Report([_result("a", True, 0.6)])
        with pytest.raises(DatasetError, match="nothing to train on"):
            export_sft(report, str(tmp_path / "t.jsonl"), min_score=0.9)

    def test_control_a_weak_pass_exports_when_the_bar_is_lower(self, tmp_path):
        report = _Report([_result("a", True, 0.6)])
        assert export_sft(report, str(tmp_path / "t.jsonl"), min_score=0.5) == 1

    def test_the_records_are_chat_format(self, tmp_path):
        out = tmp_path / "train.jsonl"
        export_sft(_Report([_result("a", True, 1.0)]), str(out))
        record = json.loads(out.read_text().splitlines()[0])
        assert [m["role"] for m in record["messages"]] == ["user", "assistant"]

    def test_a_system_prompt_is_included_when_given(self, tmp_path):
        records = sft_records(_Report([_result("a", True, 1.0)]), system_prompt="Be terse.")
        assert records[0]["messages"][0] == {"role": "system", "content": "Be terse."}

    def test_an_empty_export_raises_rather_than_writing_an_empty_file(self, tmp_path):
        """An empty file would look like a successful export."""
        with pytest.raises(DatasetError, match="nothing to train on"):
            export_sft(_Report([_result("a", False, 0.0)]), str(tmp_path / "t.jsonl"))

    def test_a_wrong_object_is_reported(self):
        with pytest.raises(DatasetError, match="Expected an EvalReport"):
            sft_records("not a report")


class TestPublicExports:
    def test_helpers_are_in_eval_package_all(self):
        """Wildcard imports and __dir__ must surface the dataset helpers."""
        import praisonaiagents.eval as evalpkg

        for name in ("load_cases", "iter_jsonl", "export_sft", "sft_records", "DatasetError"):
            assert name in evalpkg.__all__
            assert getattr(evalpkg, name) is not None
