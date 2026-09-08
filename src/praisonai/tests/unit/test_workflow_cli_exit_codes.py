"""`praisonai workflow` must report failure through its exit code.

The whole legacy handler contained zero `sys.exit`/`typer.Exit` calls and the
dispatcher hard-coded `sys.exit(0)`, so `workflow run` on a workflow whose only
step failed, and `workflow validate /nonexistent.yaml`, both exited 0. A CI job
that ran a workflow doing nothing stayed green.

These assert exit codes and return values, never message text.
"""

import os
import sys
import tempfile

import pytest

from praisonai.cli.legacy import workflow_commands


class _Host:
    """Minimal stand-in for the PraisonAI CLI object the handlers bind to."""

    def _run_yaml_workflow(self, *a, **k):
        return workflow_commands._run_yaml_workflow(self, *a, **k)

    def _validate_yaml_workflow(self, *a, **k):
        return workflow_commands._validate_yaml_workflow(self, *a, **k)

    def _get_canonical_suggestions(self, data):
        return workflow_commands._get_canonical_suggestions(self, data)

    def _create_workflow_from_template(self, *a, **k):
        return workflow_commands._create_workflow_from_template(self, *a, **k)

    def _auto_generate_workflow(self, *a, **k):
        return workflow_commands._auto_generate_workflow(self, *a, **k)

    def _load_tools(self, spec):
        return None


@pytest.fixture
def host():
    return _Host()


_GOOD_YAML = """
name: haiku-flow
agents:
  Writer:
    name: Writer
    instructions: "You write haiku"
    llm: gpt-4o-mini
steps:
  - name: haiku
    agent: Writer
    instruction: "Write a haiku"
"""


@pytest.fixture
def good_yaml(tmp_path):
    p = tmp_path / "wf.yaml"
    p.write_text(_GOOD_YAML)
    return str(p)


class TestValidateExitCode:

    def test_missing_file_returns_nonzero(self, host):
        assert host._validate_yaml_workflow("/nonexistent-workflow.yaml") != 0

    def test_valid_file_returns_zero(self, host, good_yaml):
        assert host._validate_yaml_workflow(good_yaml) == 0

    def test_unparseable_file_returns_nonzero(self, host, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("steps:\n  - name: x\n    agent: NotDefined\n")
        assert host._validate_yaml_workflow(str(bad)) != 0

    def test_handler_propagates_validate_failure(self, host):
        assert workflow_commands.handle_workflow_command(
            host, "validate", ["/nonexistent-workflow.yaml"]
        ) != 0

    def test_handler_propagates_validate_success(self, host, good_yaml):
        assert workflow_commands.handle_workflow_command(
            host, "validate", [good_yaml]
        ) == 0

    def test_non_yaml_extension_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(
            host, "validate", ["notes.txt"]
        ) != 0

    def test_missing_argument_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(
            host, "validate", []
        ) != 0


class TestRunExitCode:
    """A run the engine reports as failed must exit non-zero."""

    def _run(self, host, monkeypatch, yaml_file, status, output=None):
        class _FakeWorkflow:
            name = "haiku-flow"
            description = ""
            steps = []
            variables = {}
            planning = False
            reasoning = False
            default_input = ""

            def start(self, *a, **k):
                res = {"status": status, "output": output, "steps": []}
                if status != "completed":
                    res["error"] = "haiku: agent produced no output (None)"
                return res

        class _FakeManager:
            def __init__(self, *a, **k):
                pass

            def load_yaml(self, *a, **k):
                return _FakeWorkflow()

        import praisonaiagents.workflows as wfmod
        monkeypatch.setattr(wfmod, "WorkflowManager", _FakeManager, raising=False)
        return host._run_yaml_workflow(yaml_file, [yaml_file], {}, None)

    def test_failed_run_returns_nonzero(self, host, monkeypatch, good_yaml):
        assert self._run(host, monkeypatch, good_yaml, "failed") != 0

    def test_completed_run_returns_zero(self, host, monkeypatch, good_yaml):
        assert self._run(host, monkeypatch, good_yaml, "completed", "a haiku") == 0

    def test_missing_yaml_file_returns_nonzero(self, host):
        assert host._run_yaml_workflow(
            "/nonexistent-workflow.yaml", ["/nonexistent-workflow.yaml"], {}, None
        ) != 0

    def test_run_without_a_name_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(host, "run", []) != 0


class TestOtherActionsExitCode:

    def test_unknown_action_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(host, "banana", []) != 0

    def test_help_returns_zero(self, host):
        assert workflow_commands.handle_workflow_command(host, "help", []) == 0

    def test_show_without_a_name_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(host, "show", []) != 0

    def test_create_without_a_name_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(host, "create", []) != 0

    def test_template_with_unknown_name_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(
            host, "template", ["no-such-template"]
        ) != 0

    def test_auto_without_a_topic_returns_nonzero(self, host):
        assert workflow_commands.handle_workflow_command(host, "auto", []) != 0


class TestDispatcherPropagatesTheCode:
    """End-to-end: the shell must see a non-zero code, not just the handler."""

    def _cli(self, *args, cwd=None):
        """Run the real CLI in a subprocess and read its own exit code.

        Never through a pipe -- `cmd | tail` reports tail's status, which is
        how this class of defect stays invisible.
        """
        import subprocess

        import praisonai
        import praisonai_code
        import praisonaiagents

        roots = [
            os.path.dirname(os.path.dirname(m.__file__))
            for m in (praisonai, praisonai_code, praisonaiagents)
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(roots))
        # The legacy CLI takes a different branch when PYTEST_CURRENT_TEST is
        # set (praison_ai.py `in_test_env`), so the child must not inherit it
        # or it would not exercise the real command path.
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop("PYTEST_VERSION", None)
        return subprocess.run(
            [sys.executable, "-m", "praisonai", "workflow", *args],
            cwd=cwd, env=env, capture_output=True, text=True, timeout=300,
        )

    def test_validate_missing_file_exits_nonzero(self, tmp_path):
        proc = self._cli("validate", "/nonexistent-workflow.yaml", cwd=str(tmp_path))
        assert proc.returncode != 0, proc.stdout + proc.stderr

    def test_validate_good_file_exits_zero(self, good_yaml, tmp_path):
        proc = self._cli("validate", good_yaml, cwd=str(tmp_path))
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_list_exits_zero(self, tmp_path):
        proc = self._cli("list", cwd=str(tmp_path))
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_the_workflow_branch_no_longer_hardcodes_success(self):
        import inspect

        from praisonai_code.cli.legacy import praison_ai as legacy

        src = inspect.getsource(legacy)
        assert (
            "self.handle_workflow_command(action, action_args, workflow_vars, args)\n"
            "                sys.exit(0)"
        ) not in src, "the dispatcher still hard-codes sys.exit(0) after a workflow run"
