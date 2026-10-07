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


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("content_filtered", "content_filtered"),
        ("refused", "refused"),
        ("length_truncated", "length_truncated"),
        ("completed", None),
        ("max_steps", None),
        ("error", None),
        (None, None),
    ],
)
def test_run_block_reason_classification(reason, expected):
    assert run_cmd._run_block_reason(_StopReasonAgent(reason)) == expected


def test_run_block_reason_handles_missing_or_raising_agent():
    assert run_cmd._run_block_reason(None) is None

    class _Raising:
        @property
        def last_stop_reason(self):
            raise RuntimeError("boom")

    assert run_cmd._run_block_reason(_Raising()) is None


@pytest.mark.parametrize(
    "reason", ["content_filtered", "refused", "length_truncated"]
)
def test_report_run_blocked_exits_two_and_emits_reason_status(reason):
    output = _RecordingOutput()
    with pytest.raises(typer.Exit) as exc:
        run_cmd._report_run_blocked(output, "partial text", reason)

    # A provider block/refusal/truncation is an incomplete run (exit 2),
    # distinct from a hard failure (exit 1) and a clean completion (exit 0).
    assert exc.value.exit_code == 2

    # Machine-readable status carries the *specific* reason for --output json.
    assert output.results, "expected a result event"
    _, result_data = output.results[-1]
    assert result_data.get("status") == reason
    assert result_data.get("result") == "partial text"

    # Interactive users get a human-facing, actionable message.
    assert output.warnings, "expected a human-facing block notice"


def test_report_run_blocked_warns_only_in_non_json_mode():
    output = _RecordingOutput()
    output.is_json_mode = True
    with pytest.raises(typer.Exit):
        run_cmd._report_run_blocked(output, "", "refused")
    _, result_data = output.results[-1]
    assert result_data.get("status") == "refused"
    assert not output.warnings, "JSON mode must not print a human warning"


def test_actions_stream_reports_truncated_run_not_ok(monkeypatch):
    """A truncated run must emit ``run.result {ok: false}`` on the stream.

    Regression guard (PR #4100 review): the terminal stream event was
    previously emitted with ``ok=True`` before truncation was detected, so a
    ``--output stream-json`` consumer received a contradictory success outcome
    ahead of the ``status: "truncated"`` result. The stream ``ok`` flag must be
    ``False`` for a step-limit-truncated run, in lockstep with exit code 2.
    """
    output = _RecordingOutput()
    output.is_verbose = False

    def _noop(*args, **kwargs):
        return None

    # The actions path may print info/success while wiring tools/sessions; give
    # the recorder tolerant no-ops so an AttributeError doesn't mask the outcome.
    output.print_info = _noop
    output.print_success = _noop
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)

    class _TruncatedAgent:
        last_stop_reason = "max_steps"

        def start(self, prompt):
            return "partial summary"

    run_result_events = []

    class _Bridge:
        def emit_agent_message(self, name):
            pass

        def emit_run_result(self, result, ok=True):
            run_result_events.append(ok)

    def _fake_attach_bridge(agent, output):
        return _Bridge()

    # ``_run_prompt`` imports these from the event_bridge module at call time,
    # so patch them at the source module rather than on ``run_cmd``.
    from praisonai_code.cli.output import event_bridge as _eb
    monkeypatch.setattr(_eb, "attach_bridge", _fake_attach_bridge)
    monkeypatch.setattr(_eb, "detach_bridge", lambda *a, **k: None)

    import sys
    import types

    # The actions path builds an ``Agent`` and touches ``project_sessions``
    # (which imports ``praisonaiagents.session.store``). Provide a minimal
    # ``praisonaiagents`` package + session submodules so the run reaches the
    # truncation branch without pulling the full core install.
    pkg = types.ModuleType("praisonaiagents")
    pkg.__path__ = []  # mark as a package so submodule imports resolve
    pkg.Agent = lambda **cfg: _TruncatedAgent()
    session_pkg = types.ModuleType("praisonaiagents.session")
    session_pkg.__path__ = []
    store_mod = types.ModuleType("praisonaiagents.session.store")

    class _DefaultSessionStore:  # pragma: no cover - stub for import only
        def __init__(self, *a, **k):
            pass

    store_mod.DefaultSessionStore = _DefaultSessionStore
    hierarchy_mod = types.ModuleType("praisonaiagents.session.hierarchy")

    class _HierarchicalSessionStore:  # pragma: no cover - stub for import only
        def __init__(self, *a, **k):
            pass

    hierarchy_mod.HierarchicalSessionStore = _HierarchicalSessionStore
    monkeypatch.setitem(sys.modules, "praisonaiagents", pkg)
    monkeypatch.setitem(sys.modules, "praisonaiagents.session", session_pkg)
    monkeypatch.setitem(sys.modules, "praisonaiagents.session.store", store_mod)
    monkeypatch.setitem(
        sys.modules, "praisonaiagents.session.hierarchy", hierarchy_mod
    )

    fake_main = types.ModuleType("praisonai_code.cli.main")

    class _FakePraisonAI:
        def __init__(self, *a, **k):
            self.config_list = [{}]
            self.args = None

    fake_main.PraisonAI = _FakePraisonAI
    monkeypatch.setitem(sys.modules, "praisonai_code.cli.main", fake_main)

    with pytest.raises(typer.Exit) as exc:
        run_cmd._run_prompt(
            "do a big task",
            output_mode="actions",
            no_save=True,
        )

    # Truncation exits 2 and the terminal stream event was marked not-ok, so a
    # stream-json consumer never sees a contradictory success terminal event.
    assert exc.value.exit_code == 2
    assert run_result_events == [False]


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

    # Since #5644 a standalone text run renders in-process, so the sink here is
    # the real praisonaiagents Agent — stub it to keep the test hermetic. The
    # subject stays the warm-runtime bypass, not the render path.
    class _FakeAgent:
        def __init__(self, *a, **k):
            pass

        def start(self, prompt):
            return "done"

    monkeypatch.setattr("praisonaiagents.Agent", _FakeAgent)

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


class _CapturingAgent:
    """Fake core Agent that records its build config and the prompt it ran."""

    last_config = None
    last_prompt = None

    def __init__(self, **cfg):
        type(self).last_config = cfg

    def start(self, prompt):
        type(self).last_prompt = prompt
        return "the answer"


def _install_inprocess_agent_stubs(monkeypatch, agent_factory):
    """Wire the minimal praisonaiagents + wrapper stubs for an in-process run.

    The wrapper's ``PraisonAI`` is installed with a ``handle_direct_prompt`` that
    *raises*, so any test asserting a mode runs in-process also proves the run
    never fell through to the wrapper delegation path (the exact #5665 bug).
    """
    import sys
    import types

    pkg = types.ModuleType("praisonaiagents")
    pkg.__path__ = []
    pkg.Agent = agent_factory

    class _MemoryConfig:  # pragma: no cover - simple record stub
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.auto_save = kwargs.get("auto_save")
            self.session_id = kwargs.get("session_id")

    pkg.MemoryConfig = _MemoryConfig
    monkeypatch.setitem(sys.modules, "praisonaiagents", pkg)

    fake_main = types.ModuleType("praisonai_code.cli.main")

    class _FailingWrapper:
        def __init__(self, *a, **k):
            self.config_list = [{}]
            self.args = None

        def handle_direct_prompt(self, prompt):  # pragma: no cover - must not run
            raise AssertionError(
                "structured modes must run in-process, not via the wrapper"
            )

    fake_main.PraisonAI = _FailingWrapper
    monkeypatch.setitem(sys.modules, "praisonai_code.cli.main", fake_main)


def _make_output(monkeypatch, *, json_mode=False):
    output = _RecordingOutput()
    output.is_json_mode = json_mode
    output.is_verbose = False
    output.mode = None
    _noop = lambda *a, **k: None
    output.print_info = _noop
    output.print_success = _noop
    output.emit_start = _noop
    output.emit_event = _noop
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    return output


@pytest.mark.parametrize("mode", ["actions", "json", "stream", "stream-json"])
def test_structured_modes_run_in_process_not_wrapper(monkeypatch, mode, capsys):
    """Regression guard for #5665: json/stream/stream-json dispatch in-process.

    If the dispatch condition were reverted to ``output_mode == "actions"`` the
    other three modes would reach the wrapper's ``handle_direct_prompt`` stub,
    which raises — so this fails loudly on the exact bug the PR fixes. It also
    pins the per-mode stdout contract (json envelope / stream text / no raw text
    for stream-json).
    """
    _CapturingAgent.last_prompt = None
    _install_inprocess_agent_stubs(monkeypatch, _CapturingAgent)
    _make_output(monkeypatch, json_mode=(mode == "json"))

    run_cmd._run_prompt("summarise this", output_mode=mode, no_save=True)

    # The in-process Agent actually ran (the model path, not the wrapper).
    assert _CapturingAgent.last_prompt == "summarise this"

    out = capsys.readouterr().out
    if mode == "json":
        import json as _json
        assert _json.loads(out.strip()) == {"result": "the answer"}
    elif mode == "stream":
        assert out.strip() == "the answer"
    elif mode == "actions":
        # The core actions preset renders its own output; the CLI prints nothing.
        assert out.strip() == ""
    else:  # stream-json: NDJSON framing is owned by the event bridge, no raw text
        assert "the answer" not in out


@pytest.mark.parametrize("mode", ["json", "stream"])
def test_truncated_run_surfaces_partial_answer_before_exit(monkeypatch, mode, capsys):
    """Greptile P1: a truncated json/stream run must still print its partial text.

    The truncated/blocked reporters raise ``typer.Exit(2)``; the mode-specific
    stdout payload must be emitted *before* that exit so a ``--output json`` pipe
    is not empty and a ``--output stream`` user keeps the partial answer.
    """

    class _TruncatedAgent(_CapturingAgent):
        last_stop_reason = "max_steps"

        def start(self, prompt):
            type(self).last_prompt = prompt
            return "partial summary"

    _install_inprocess_agent_stubs(monkeypatch, _TruncatedAgent)
    _make_output(monkeypatch, json_mode=(mode == "json"))

    with pytest.raises(typer.Exit) as exc:
        run_cmd._run_prompt("big task", output_mode=mode, no_save=True)

    assert exc.value.exit_code == 2
    out = capsys.readouterr().out
    if mode == "json":
        import json as _json
        assert _json.loads(out.strip()) == {"result": "partial summary"}
    else:
        assert out.strip() == "partial summary"


def test_inprocess_honors_explicit_memory_flag(monkeypatch):
    """Greptile P1: `--memory` must reach the Agent even without a session name.

    Routing json/stream/stream-json in-process previously dropped the explicit
    memory flag (``build_cli_memory_config`` returns None without a session /
    auto-save); the wrapper path used to set ``memory=True``. Keep that honored.
    """
    _CapturingAgent.last_config = None
    _install_inprocess_agent_stubs(monkeypatch, _CapturingAgent)
    _make_output(monkeypatch, json_mode=True)

    run_cmd._run_prompt(
        "remember this", output_mode="json", memory=True, no_save=True
    )

    assert _CapturingAgent.last_config.get("memory") is True


def test_inprocess_no_memory_flag_leaves_memory_unset(monkeypatch):
    """Without `--memory` (and no session), the Agent is built memory-free."""
    _CapturingAgent.last_config = None
    _install_inprocess_agent_stubs(monkeypatch, _CapturingAgent)
    _make_output(monkeypatch, json_mode=True)

    run_cmd._run_prompt("no memory", output_mode="json", no_save=True)

    assert "memory" not in _CapturingAgent.last_config
