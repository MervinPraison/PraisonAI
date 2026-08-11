"""Tests for the trials→SFT exporter (``data/export_trials.py``).

The report is duck-typed over plain dicts (the serialised contract with the
sibling core trials engine), so these fixtures build reports as dicts.
"""
import json

import pytest

from praisonai_train.data import ExportSummary, export_trials


def _attempt(role_text, score, *, passed=None, tools=False):
    """A minimal attempt record: system+user+assistant messages, plus a score."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "2+2?"},
        {"role": "assistant", "content": role_text},
    ]
    a = {"messages": messages, "score": score}
    if passed is not None:
        a["passed"] = passed
    if tools:
        a["tool_calls"] = [{"name": "calc", "args": {}}]
    return a


def _report(cases, package="demo"):
    return {"package": package, "source": "trials.json", "cases": cases}


def _read_jsonl(path):
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


# ── selection: only_passed (default) ──────────────────────────────────────────

def test_export_only_passed_default(tmp_path):
    """Failed and unscored attempts are skipped with the right counters."""
    case = {
        "case_id": "c1",
        "attempts": [
            _attempt("4", score=1.0, passed=True),   # kept
            _attempt("5", score=0.0, passed=False),  # skipped_failed
            _attempt("?", score=None),               # skipped_unscored
        ],
    }
    out = tmp_path / "train.jsonl"
    summary = export_trials(_report([case]), out, frontier_only=False)

    assert isinstance(summary, ExportSummary)
    assert summary.written == 1
    assert summary.skipped_failed == 1
    assert summary.skipped_unscored == 1
    rows = _read_jsonl(out)
    assert rows[0]["conversations"][-1]["content"] == "4"


# ── selection: frontier_only (default) ────────────────────────────────────────

def test_frontier_only_default(tmp_path):
    """A saturated (all-pass) case contributes zero rows by default."""
    saturated = {
        "case_id": "sat",
        "attempts": [
            _attempt("4", score=1.0, passed=True),
            _attempt("4", score=1.0, passed=True),
        ],
    }
    out = tmp_path / "train.jsonl"
    summary = export_trials(_report([saturated]), out)  # frontier_only default True
    assert summary.written == 0
    assert summary.skipped_saturated == 2

    # With --include-saturated (frontier_only=False) it now exports.
    out2 = tmp_path / "train2.jsonl"
    summary2 = export_trials(_report([saturated]), out2, frontier_only=False)
    assert summary2.written == 2


# ── selection: tool-using runs excluded ───────────────────────────────────────

def test_tool_runs_excluded_and_counted(tmp_path):
    case = {
        "case_id": "c1",
        "attempts": [
            _attempt("4", score=1.0, passed=True),               # kept
            _attempt("4", score=1.0, passed=True, tools=True),   # skipped_tool_runs
        ],
    }
    out = tmp_path / "train.jsonl"
    summary = export_trials(_report([case]), out, frontier_only=False)
    assert summary.written == 1
    assert summary.skipped_tool_runs == 1


# ── shape: ShareGPT conversations ─────────────────────────────────────────────

def test_conversation_shape_sharegpt(tmp_path):
    """Rows are ShareGPT ``conversations`` with role/content dicts, truncated at
    the final assistant turn."""
    case = {
        "case_id": "c1",
        "attempts": [
            _attempt("4", score=1.0, passed=True),
            _attempt("5", score=0.0, passed=False),
        ],
    }
    out = tmp_path / "train.jsonl"
    export_trials(_report([case]), out, frontier_only=False)
    rows = _read_jsonl(out)
    convo = rows[0]["conversations"]
    assert [t["role"] for t in convo] == ["system", "user", "assistant"]
    assert all({"role", "content"} <= set(t) for t in convo)
    assert convo[-1]["role"] == "assistant"


def test_trailing_non_assistant_truncated(tmp_path):
    """Turns after the final assistant message are dropped."""
    a = _attempt("4", score=1.0, passed=True)
    a["messages"].append({"role": "user", "content": "thanks"})
    out = tmp_path / "train.jsonl"
    export_trials(_report([{"case_id": "c1", "attempts": [a,
                  _attempt("x", score=0.0, passed=False)]}]),
                  out, frontier_only=False)
    convo = _read_jsonl(out)[0]["conversations"]
    assert convo[-1]["role"] == "assistant"


# ── provenance sidecar ────────────────────────────────────────────────────────

def test_provenance_sidecar(tmp_path):
    """Every emitted line maps to case id + attempt index + score."""
    case = {
        "case_id": "c1",
        "attempts": [
            _attempt("4", score=0.9, passed=True),
            _attempt("5", score=0.0, passed=False),
        ],
    }
    out = tmp_path / "train.jsonl"
    export_trials(_report([case]), out, frontier_only=False)
    meta = json.loads((tmp_path / "train.jsonl.meta.json").read_text())

    assert meta["package"] == "demo"
    assert meta["options"]["only_passed"] is True
    assert len(meta["lines"]) == 1
    line = meta["lines"][0]
    assert line["case_id"] == "c1"
    assert line["attempt_index"] == 0
    assert line["score"] == 0.9
    assert meta["summary"]["written"] == 1


# ── determinism ───────────────────────────────────────────────────────────────

def test_deterministic_output(tmp_path):
    """Same report → byte-identical JSONL (case order, then attempt order)."""
    cases = [
        {"case_id": "c1", "attempts": [
            _attempt("a", score=1.0, passed=True),
            _attempt("b", score=0.0, passed=False)]},
        {"case_id": "c2", "attempts": [
            _attempt("c", score=1.0, passed=True),
            _attempt("d", score=0.0, passed=False)]},
    ]
    o1 = tmp_path / "a.jsonl"
    o2 = tmp_path / "b.jsonl"
    export_trials(_report(cases), o1, frontier_only=False)
    export_trials(_report(cases), o2, frontier_only=False)
    assert o1.read_bytes() == o2.read_bytes()


# ── --all includes unscored attempts ─────────────────────────────────────────

def test_all_includes_unscored(tmp_path):
    """With only_passed=False (--all), unscored attempts are exported, not dropped."""
    case = {
        "case_id": "c1",
        "attempts": [
            _attempt("4", score=1.0, passed=True),  # kept
            _attempt("?", score=None),              # kept under --all
        ],
    }
    out = tmp_path / "train.jsonl"
    summary = export_trials(
        _report([case]), out, only_passed=False, frontier_only=False)
    assert summary.written == 2
    assert summary.skipped_unscored == 0


# ── alpaca fallback ───────────────────────────────────────────────────────────

def test_alpaca_format(tmp_path):
    case = {"case_id": "c1", "attempts": [
        _attempt("4", score=1.0, passed=True),
        _attempt("x", score=0.0, passed=False)]}
    out = tmp_path / "train.jsonl"
    export_trials(_report([case]), out, frontier_only=False, format="alpaca")
    row = _read_jsonl(out)[0]
    assert set(row) == {"instruction", "input", "output"}
    assert row["output"] == "4"


def test_alpaca_keeps_user_prompt_with_system(tmp_path):
    """A system+user conversation keeps the user prompt in Alpaca ``input``."""
    case = {"case_id": "c1", "attempts": [
        _attempt("4", score=1.0, passed=True),
        _attempt("x", score=0.0, passed=False)]}
    out = tmp_path / "train.jsonl"
    export_trials(_report([case]), out, frontier_only=False, format="alpaca")
    row = _read_jsonl(out)[0]
    assert row["instruction"] == "You are helpful."
    assert row["input"] == "2+2?"  # the sole user prompt is never dropped
    assert row["output"] == "4"


def test_alpaca_no_system_uses_first_user_as_instruction(tmp_path):
    """Without a system turn, first user is instruction and the rest is input."""
    a = {"messages": [
        {"role": "user", "content": "translate"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "bonjour"},
    ], "score": 1.0, "passed": True}
    out = tmp_path / "train.jsonl"
    export_trials(_report([{"case_id": "c1", "attempts": [
        a, _attempt("x", score=0.0, passed=False)]}]),
        out, frontier_only=False, format="alpaca")
    row = _read_jsonl(out)[0]
    assert row["instruction"] == "translate"
    assert row["input"] == "hello"
    assert row["output"] == "bonjour"


# ── score threshold (no explicit passed flag) ─────────────────────────────────

def test_score_below_threshold_is_failed(tmp_path):
    """A positive score below the report's threshold counts as a failure."""
    case = {"case_id": "c1", "attempts": [
        {"messages": _attempt("4", 1.0)["messages"], "score": 0.9, "pass_threshold": 0.5},
        {"messages": _attempt("5", 0.0)["messages"], "score": 0.3, "pass_threshold": 0.5},
    ]}
    out = tmp_path / "train.jsonl"
    summary = export_trials(_report([case]), out, frontier_only=False)
    assert summary.written == 1  # only the 0.9 passes the 0.5 bar
    assert summary.skipped_failed == 1
    assert _read_jsonl(out)[0]["conversations"][-1]["content"] == "4"


def test_invalid_format_raises(tmp_path):
    with pytest.raises(ValueError):
        export_trials(_report([]), tmp_path / "x.jsonl", format="bogus")


# ── loads from a path ─────────────────────────────────────────────────────────

def test_loads_report_from_path(tmp_path):
    case = {"case_id": "c1", "attempts": [
        _attempt("4", score=1.0, passed=True),
        _attempt("x", score=0.0, passed=False)]}
    report_path = tmp_path / "trials.json"
    report_path.write_text(json.dumps(_report([case])))
    out = tmp_path / "train.jsonl"
    summary = export_trials(str(report_path), out, frontier_only=False)
    assert summary.written == 1
