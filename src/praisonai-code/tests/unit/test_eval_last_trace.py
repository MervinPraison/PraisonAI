"""Tests for ``praisonai eval last-trace`` (issue #5622).

Grade the last completed traced run from the CLI without a manual JSON export.
"""

import json

from typer.testing import CliRunner

from praisonai_code.cli.commands.eval import app


def _write_pointer(tmp_path, monkeypatch, trace_path):
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    from praisonaiagents.trace import record_completed_run

    record_completed_run(trace_path)


def test_last_trace_missing_pointer_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISON_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["last-trace"])
    assert result.exit_code == 2
    assert "No completed traced run" in result.output


def test_last_trace_pass_exits_0(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(
        "\n".join(
            [
                json.dumps({"event_type": "tool_start", "tool_name": "search"}),
                json.dumps({"event_type": "tool_end", "tool_name": "search"}),
            ]
        ),
        encoding="utf-8",
    )
    _write_pointer(tmp_path, monkeypatch, trace)

    result = CliRunner().invoke(app, ["last-trace", "--min-tool-calls", "1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["passed"] is True
    assert payload["tool_call_count"] == 1


def test_last_trace_fail_exits_1(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("", encoding="utf-8")
    _write_pointer(tmp_path, monkeypatch, trace)

    result = CliRunner().invoke(app, ["last-trace", "--min-tool-calls", "1", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["passed"] is False


def test_last_trace_malformed_trace_exits_1(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    trace.write_text("{not valid json", encoding="utf-8")
    _write_pointer(tmp_path, monkeypatch, trace)

    result = CliRunner().invoke(app, ["last-trace"])
    assert result.exit_code == 1
    assert "Malformed trace" in result.output


def test_last_trace_json_array_form(tmp_path, monkeypatch):
    trace = tmp_path / "trace.json"
    trace.write_text(
        json.dumps(
            [
                {"event_type": "tool_start", "tool_name": "read_file"},
                {"event_type": "tool_start", "tool_name": "write_file"},
            ]
        ),
        encoding="utf-8",
    )
    _write_pointer(tmp_path, monkeypatch, trace)

    result = CliRunner().invoke(app, ["last-trace", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["tool_call_count"] == 2
