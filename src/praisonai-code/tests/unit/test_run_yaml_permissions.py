"""Tests: YAML workflow runs gain permission gating on the unified `run` path.

`praisonai run workflow.yaml` reaches the Typer `run` engine (`_run_from_file`),
which already threads session continuity and emits structured `--output` events.
This verifies the remaining parity gap is closed: approval/permission flags
(`--approval`, `--approve-all-tools`, `--allow`/`--deny`) are forwarded into the
YAML engine's ``args`` so YAML agents are permission-gated exactly like
single-agent `run "<prompt>"`, instead of silently bypassing the approval gate.
"""

import sys
from types import ModuleType

import pytest

from praisonai_code.cli.commands import run as run_cmd


class _RecordingOutput:
    def __init__(self):
        self.is_json_mode = False

    def print_info(self, *a, **k):
        pass

    def print_warning(self, *a, **k):
        pass

    def print_error(self, *a, **k):
        pass

    def print_success(self, *a, **k):
        pass

    def emit_result(self, message=None, data=None):
        pass

    def emit_error(self, message=None, data=None):
        pass


class _FakePraisonAI:
    """Captures the ``args`` object threaded onto the YAML engine."""

    last_instance = None

    def __init__(self, agent_file=None, framework=None):
        self.agent_file = agent_file
        self.framework = framework
        self.config_list = [{"model": "gpt-4o"}]
        self.args = None
        _FakePraisonAI.last_instance = self

    def run(self):
        return "workflow result"


@pytest.fixture(autouse=True)
def _patch_engine(monkeypatch):
    # Route the YAML run through a fake engine so no LLM/network is hit and we
    # can assert exactly which permission/session args were threaded through.
    monkeypatch.setattr(
        "praisonai_code.cli.main.PraisonAI", _FakePraisonAI, raising=False
    )
    monkeypatch.setattr(
        run_cmd, "get_output_controller", lambda: _RecordingOutput()
    )
    yield
    _FakePraisonAI.last_instance = None


def test_explicit_approval_is_threaded_into_yaml_args():
    run_cmd._run_from_file(
        "workflow.yaml",
        no_save=True,
        approval="console",
        approve_all_tools=True,
        approval_timeout="30",
    )
    args = _FakePraisonAI.last_instance.args
    assert args is not None
    assert args.approval == "console"
    assert args.approve_all_tools is True
    assert args.approval_timeout == "30"


def test_permission_patterns_default_to_console_backend():
    # --allow/--deny rules (permissions_config) with no explicit --approval must
    # still activate a console backend so deny/ask patterns are enforced.
    run_cmd._run_from_file(
        "workflow.yaml",
        no_save=True,
        permissions_config={"bash:rm *": "deny"},
    )
    args = _FakePraisonAI.last_instance.args
    assert args is not None
    assert args.approval == "console"


def test_no_permission_flags_leaves_approval_unset():
    # Backward compatible: a plain --no-save YAML run with no session and no
    # permission flags threads no args at all, so the legacy engine's
    # getattr(..., 'approval', None) default preserves prior behaviour exactly.
    run_cmd._run_from_file("workflow.yaml", no_save=True)
    assert _FakePraisonAI.last_instance.args is None


def test_session_run_without_permission_flags_has_no_approval():
    # A session run builds an args object for continuity, but must not carry an
    # approval override when no approval/permission flags were supplied.
    run_cmd._run_from_file("workflow.yaml")  # no_save defaults False -> auto_save
    args = _FakePraisonAI.last_instance.args
    assert args is not None
    assert not hasattr(args, "approval")
    assert not hasattr(args, "approve_all_tools")


class _PreservedArgs:
    """Args pre-set on ``praison.args`` by the YAML ``run`` path."""

    def __init__(self, **kw):
        self.approval = None
        self.approve_all_tools = None
        self.approval_timeout = None
        self.output = None
        self.cli_project_sessions = False
        for k, v in kw.items():
            setattr(self, k, v)


def _run_main_preserving(monkeypatch, preserved):
    """Drive the *real* legacy ``PraisonAI.main()`` args-preservation boundary.

    parse_args() returns a fresh namespace (as it does after real CLI parsing);
    an invalid framework forces an early ``sys.exit`` right after the preservation
    loop and ``self.args = args`` assignment, so we can assert exactly which
    fields survived the reparse without executing any workflow/LLM.
    """
    from praisonai_code.cli.legacy import praison_ai as legacy

    class _Fresh:
        def __init__(self):
            self.framework = "definitely-not-a-real-framework"
            self.prompt_flag = None

    praison = legacy.PraisonAI.__new__(legacy.PraisonAI)
    praison.agent_file = "workflow.yaml"
    praison.framework = ""
    praison.config_list = [{"model": "gpt-4o"}]
    praison.args = preserved

    monkeypatch.setattr(praison, "parse_args", lambda: (_Fresh(), []))
    monkeypatch.setattr(legacy, "_load_env_once", lambda: None, raising=False)
    monkeypatch.setattr(legacy, "_ensure_availability_flags", lambda: None, raising=False)

    class _Boom(Exception):
        pass

    def _raise_available(_fw):
        raise ImportError("stop after preservation")

    monkeypatch.setattr(
        legacy, "_fw_validators_module",
        lambda: type("M", (), {"assert_framework_available": staticmethod(_raise_available)}),
        raising=False,
    )
    monkeypatch.setattr(legacy.sys, "exit", lambda *a: (_ for _ in ()).throw(_Boom()))

    with pytest.raises(_Boom):
        praison.main()
    return praison.args


def test_main_preserves_approval_across_parse_args_boundary(monkeypatch):
    # Regression: parse_args() replaces args, so approval settings threaded onto
    # praison.args must be re-applied or YAML runs silently bypass the gate.
    preserved = _PreservedArgs(
        approval="console", approve_all_tools=True, approval_timeout="30",
    )
    args = _run_main_preserving(monkeypatch, preserved)
    assert args.approval == "console"
    assert args.approve_all_tools is True
    assert args.approval_timeout == "30"


def test_main_preserves_approval_without_session_flag(monkeypatch):
    # --allow/--deny with --no-save sets approval but NOT cli_project_sessions;
    # the approval gate must still survive the reparse independently of sessions.
    preserved = _PreservedArgs(approval="console", cli_project_sessions=False)
    args = _run_main_preserving(monkeypatch, preserved)
    assert args.approval == "console"


def test_main_preserves_output_across_parse_args_boundary(monkeypatch):
    preserved = _PreservedArgs(output="stream-json")
    args = _run_main_preserving(monkeypatch, preserved)
    assert args.output == "stream-json"


def test_profiled_yaml_path_forwards_output_mode(monkeypatch):
    class _Profiler:
        def __init__(self, config):
            pass

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    profiler_module = ModuleType("praisonai_code.cli.features.cli_profiler")
    profiler_module.CLIProfileConfig = lambda **kwargs: kwargs
    profiler_module.CLIProfiler = _Profiler
    monkeypatch.setitem(
        sys.modules, "praisonai_code.cli.features.cli_profiler", profiler_module
    )

    run_cmd._run_from_file_profiled(
        "workflow.yaml",
        no_save=True,
        output_mode="stream-json",
    )

    args = _FakePraisonAI.last_instance.args
    assert args is not None
    assert args.output == "stream-json"
