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
        self.warnings = []
        self.is_json_mode = False

    def emit_result(self, message=None, data=None):
        self.results.append((message, data))

    def emit_error(self, message=None, data=None):
        self.errors.append((message, data))

    def print_error(self, message, code=None, remediation=None):
        self.printed_errors.append((message, code, remediation))

    def print_warning(self, message):
        self.warnings.append(message)


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


class _StopReasonAgent:
    """Minimal agent exposing a ``last_stop_reason`` like the core Agent."""

    def __init__(self, reason):
        self.last_stop_reason = reason


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("max_steps", True),
        ("completed", False),
        ("error", False),
        (None, False),
    ],
)
def test_run_was_truncated_classification(reason, expected):
    assert run_cmd._run_was_truncated(_StopReasonAgent(reason)) is expected


def test_run_was_truncated_handles_missing_or_raising_agent():
    # No agent, or an accessor that raises, must be treated as not-truncated so
    # the completed/failed contract is preserved unchanged.
    assert run_cmd._run_was_truncated(None) is False

    class _Raising:
        @property
        def last_stop_reason(self):
            raise RuntimeError("boom")

    assert run_cmd._run_was_truncated(_Raising()) is False


def test_report_run_truncated_exits_two_and_emits_truncated_status():
    output = _RecordingOutput()
    with pytest.raises(typer.Exit) as exc:
        run_cmd._report_run_truncated(output, "partial summary")

    # Distinct from a hard failure (exit 1) and a clean completion (exit 0).
    assert exc.value.exit_code == 2

    # Machine-readable truncated object that preserves the summary text.
    assert output.results, "expected a result event"
    _, result_data = output.results[-1]
    assert result_data.get("status") == "truncated"
    assert result_data.get("result") == "partial summary"

    # An interactive (non-JSON) user gets a one-line notice that the answer is
    # a wrap-up, not a finished task.
    assert output.warnings, "expected a human-facing truncation notice"


def test_report_run_truncated_warns_only_in_non_json_mode():
    output = _RecordingOutput()
    output.is_json_mode = True
    with pytest.raises(typer.Exit):
        run_cmd._report_run_truncated(output, "partial summary")
    # JSON consumers get the machine-readable status but no human warning noise.
    _, result_data = output.results[-1]
    assert result_data.get("status") == "truncated"
    assert not output.warnings, "JSON mode must not print a human warning"


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


def test_try_attach_runtime_exits_nonzero_on_empty_runtime_result(monkeypatch):
    """A warm-runtime run returning an empty result must fail, not exit 0.

    Regression guard: the warm-runtime attach path previously reported success
    unconditionally, so a swallowed failure on the runtime still exited 0 and
    broke CI/scripted failure detection.
    """
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)

    class _Descriptor:
        pass

    class _RuntimeUnavailable(Exception):
        pass

    class _RuntimeClient:
        def __init__(self, descriptor):
            pass

        def run(self, prompt, model=None, session_id=None, event_id=None):
            return None

    import sys
    import types

    fake_runtime = types.ModuleType("praisonai_code.runtime")
    fake_runtime.get_runtime_descriptor = lambda require_compatible=True: _Descriptor()
    fake_runtime.RuntimeClient = _RuntimeClient
    fake_runtime.RuntimeUnavailable = _RuntimeUnavailable
    monkeypatch.setitem(sys.modules, "praisonai_code.runtime", fake_runtime)

    with pytest.raises(typer.Exit) as exc:
        run_cmd._try_attach_runtime(
            "hello",
            model=None,
            output_mode=None,
            session_id=None,
        )

    assert exc.value.exit_code == 1
    assert output.printed_errors, "expected a printed failure"
    assert output.printed_errors[-1][1] == "run_failed"


def test_append_system_prompt_bypasses_warm_runtime(monkeypatch):
    """`--append-system-prompt` must run in-process, never via the warm runtime.

    Regression guard (issue #3743 / PR #3756 review): the warm runtime is a
    separate process that never received the CLI's PRAISONAI_APPEND_SYSTEM_PROMPT
    export and reuses a cached agent, so forwarding a run with an append suffix
    would silently drop it. The in-process path applies the suffix, so the run
    must stay in-process when the suffix is set.
    """
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)

    attach_calls = []

    def _fake_attach(*args, **kwargs):
        attach_calls.append((args, kwargs))
        return True  # Pretend the runtime handled it, so a bug would short-circuit.

    monkeypatch.setattr(run_cmd, "_try_attach_runtime", _fake_attach)

    class _FakePraisonAI:
        def __init__(self, *a, **k):
            self.config_list = [{}]
            self.args = None

        def handle_direct_prompt(self, prompt):
            return "done"

    import sys
    import types

    fake_main = types.ModuleType("praisonai_code.cli.main")
    fake_main.PraisonAI = _FakePraisonAI
    monkeypatch.setitem(sys.modules, "praisonai_code.cli.main", fake_main)

    run_cmd._run_prompt(
        "refactor this",
        no_save=True,
        append_system_prompt="Always answer in French",
    )

    assert not attach_calls, "append-system-prompt run must not forward to warm runtime"


def test_no_append_still_allows_warm_runtime(monkeypatch):
    """Without an append suffix, an eligible no-save run still attaches warm.

    Complements the guard above: the append-suffix gate must not accidentally
    disable the warm-runtime fast path for ordinary runs.
    """
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)

    attach_calls = []

    def _fake_attach(*args, **kwargs):
        attach_calls.append((args, kwargs))
        return True

    monkeypatch.setattr(run_cmd, "_try_attach_runtime", _fake_attach)

    class _FakePraisonAI:
        def __init__(self, *a, **k):
            self.config_list = [{}]
            self.args = None

        def handle_direct_prompt(self, prompt):
            return "done"

    import sys
    import types

    fake_main = types.ModuleType("praisonai_code.cli.main")
    fake_main.PraisonAI = _FakePraisonAI
    monkeypatch.setitem(sys.modules, "praisonai_code.cli.main", fake_main)

    run_cmd._run_prompt("refactor this", no_save=True)

    assert attach_calls, "an eligible no-save run should attach to the warm runtime"
