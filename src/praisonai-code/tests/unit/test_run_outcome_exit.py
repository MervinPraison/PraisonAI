"""Tests for run-outcome exit semantics on `praisonai run` (issue #3344).

`run.py` must exit non-zero and emit a machine-readable failure object when an
agent run does not produce a result (swallowed LLM/auth error, guardrail block,
tool failure, or `max_iter` without completion), instead of always reporting
success and exiting 0. A genuine (non-empty) result still exits 0 with unchanged
text output.
"""

import pytest
import typer

from praisonai_code.cli.commands import run as run_cmd


class _RecordingOutput:
    """Minimal output controller capturing failure-reporting calls."""

    def __init__(self):
        self.results = []
        self.errors = []
        self.printed_errors = []
        self.is_json_mode = False

    def emit_result(self, message=None, data=None):
        self.results.append((message, data))

    def emit_error(self, message=None, data=None):
        self.errors.append((message, data))

    def print_error(self, message, code=None, remediation=None):
        self.printed_errors.append((message, code, remediation))


@pytest.mark.parametrize(
    "result,expected",
    [
        ("A real answer", True),
        ("  spaced answer  ", True),
        ({"data": 1}, True),
        (None, False),
        ("", False),
        ("   ", False),
    ],
)
def test_run_succeeded_classification(result, expected):
    assert run_cmd._run_succeeded(result) is expected


def test_report_run_failure_exits_nonzero_and_emits_status():
    output = _RecordingOutput()
    with pytest.raises(typer.Exit) as exc:
        run_cmd._report_run_failure(output)

    assert exc.value.exit_code == 1

    # Machine-readable failure object for --output json consumers.
    assert output.results, "expected a result event"
    _, result_data = output.results[-1]
    assert result_data.get("status") == "failed"

    assert output.errors, "expected an error event"
    _, error_data = output.errors[-1]
    assert error_data.get("status") == "failed"

    # Human-facing error with a code and an actionable remediation.
    assert output.printed_errors, "expected a printed error"
    _, code, remediation = output.printed_errors[-1]
    assert code == "run_failed"
    assert remediation
