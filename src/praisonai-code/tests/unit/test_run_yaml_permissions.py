"""Tests: YAML workflow runs gain permission gating on the unified `run` path.

`praisonai run workflow.yaml` reaches the Typer `run` engine (`_run_from_file`),
which already threads session continuity and emits structured `--output` events.
This verifies the remaining parity gap is closed: approval/permission flags
(`--approval`, `--approve-all-tools`, `--allow`/`--deny`) are forwarded into the
YAML engine's ``args`` so YAML agents are permission-gated exactly like
single-agent `run "<prompt>"`, instead of silently bypassing the approval gate.
"""

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
