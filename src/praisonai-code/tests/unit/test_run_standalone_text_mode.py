"""Regression tests for standalone text-mode in-process rendering (issue #5644).

`pip install praisonai-code` alone used to gate the default human-readable run
(`run "prompt"`, `--output plain/verbose/silent`) with an install hint, because
those modes delegated to the wrapper's `handle_direct_prompt`. These tests pin
the fixed behaviour: on a standalone install the text modes render in-process
from the same Agent loop the structured `--output actions` path already uses,
while a wrapper-installed environment still delegates (unchanged).

The Agent is faked so the tests never touch a provider; the wrapper is faked at
the module boundary the way `test_run_image_attachment.py` does it.
"""

import sys
import types

import pytest

from praisonai_code.cli.commands import run as run_cmd


class _RecordingOutput:
    def __init__(self):
        self.results = []
        self.errors = []
        self.is_json_mode = False

    def emit_result(self, message=None, data=None):
        self.results.append((message, data))

    def emit_error(self, message=None, data=None):
        pass

    def print_info(self, *a, **k):
        pass

    def print_warning(self, *a, **k):
        pass

    def print_error(self, *a, **k):
        pass


def _install_fake_praisonai(monkeypatch):
    """Install a fake PraisonAI that records delegation of a text run."""
    captured = {}

    class _FakePraisonAI:
        def __init__(self, *a, **k):
            self.config_list = [{}]
            self.args = None

        def handle_direct_prompt(self, prompt):
            captured["prompt"] = prompt
            return "wrapper answer"

    fake_main = types.ModuleType("praisonai_code.cli.main")
    fake_main.PraisonAI = _FakePraisonAI
    monkeypatch.setitem(sys.modules, "praisonai_code.cli.main", fake_main)
    return captured


def _install_fake_agent(monkeypatch):
    """Replace praisonaiagents.Agent with a recorder; returns the captured config."""
    captured = {}

    class _FakeAgent:
        def __init__(self, **config):
            captured["config"] = config

        def start(self, prompt):
            captured["prompt"] = prompt
            return "agent answer"

    monkeypatch.setattr("praisonaiagents.Agent", _FakeAgent)
    return captured


@pytest.fixture
def standalone(monkeypatch):
    """A standalone install: wrapper not available, warm runtime not reachable."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: False
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    return output


def test_standalone_default_run_renders_in_process(standalone, monkeypatch, capsys):
    """`run "hi"` on a standalone install runs the in-process Agent and prints."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True)

    assert captured["prompt"] == "hi"
    assert captured["config"]["output"] == "minimal"
    assert "agent answer" in capsys.readouterr().out


@pytest.mark.parametrize(
    "mode,preset", [(None, "minimal"), ("plain", "minimal"), ("silent", "minimal"), ("verbose", "verbose")]
)
def test_text_modes_map_to_agent_presets(standalone, monkeypatch, mode, preset):
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode=mode)

    assert captured["config"]["output"] == preset


def test_verbose_run_lets_the_agent_render(standalone, monkeypatch, capsys):
    """The verbose preset renders the response itself; the CLI stays quiet."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="verbose")

    assert captured["config"]["output"] == "verbose"
    assert "agent answer" not in capsys.readouterr().out


def test_memory_flag_is_honoured_in_process(standalone, monkeypatch):
    """--memory must not be silently dropped by the in-process text path."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, memory=True)

    assert captured["config"]["memory"] is True


def test_wrapper_installed_text_run_still_delegates(monkeypatch, capsys):
    """With the wrapper installed, a text run delegates exactly as before."""
    monkeypatch.setattr(
        "praisonai_code._wrapper_bridge.wrapper_available", lambda: True
    )
    monkeypatch.setattr(run_cmd, "_try_attach_runtime", lambda *a, **k: False)
    output = _RecordingOutput()
    monkeypatch.setattr(run_cmd, "get_output_controller", lambda: output)
    captured = _install_fake_praisonai(monkeypatch)
    agent_started = _install_fake_agent(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True)

    assert captured["prompt"] == "hi"
    assert "prompt" not in agent_started  # the in-process Agent was not used
    assert "wrapper answer" in capsys.readouterr().out


def test_structured_actions_run_unchanged(standalone, monkeypatch):
    """--output actions keeps its structured preset and in-process dispatch."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, output_mode="actions")

    assert captured["config"]["output"] == "actions"


def test_permission_policy_is_enforced_in_process(standalone, monkeypatch):
    """--allow/--deny/--permissions must gate the run, not be silently dropped."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt(
        "rm -rf build",
        no_save=True,
        permissions_config={"bash:rm *": "deny"},
    )

    approval = captured["config"].get("approval")
    assert approval is not None, "a permission policy must gate the run"
    permissions = getattr(approval, "permissions", approval)
    assert permissions and "bash:rm *" in permissions


def test_plain_standalone_run_install_no_approval(standalone, monkeypatch):
    """A run without permission flags must not gain an approval backend."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True)

    assert captured["config"].get("approval") is None


def test_verbose_flag_selects_the_verbose_preset(standalone, monkeypatch, capsys):
    """`--verbose` folds into the Agent preset, as the wrapper text path does.

    The flag is separate from `--output`, so without this a standalone default
    run would take the silent preset and render differently from the very same
    command on a wrapper-installed install.
    """
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, verbose=True)

    assert captured["config"]["output"] == "verbose"
    # The verbose preset renders the response itself; the CLI must not print it
    # a second time.
    assert "agent answer" not in capsys.readouterr().out


def test_explicit_output_mode_wins_over_verbose_flag(standalone, monkeypatch):
    """An explicit `--output plain` is not overridden by `--verbose`."""
    captured = _install_fake_agent(monkeypatch)
    _install_fake_praisonai(monkeypatch)

    run_cmd._run_prompt("hi", no_save=True, verbose=True, output_mode="plain")

    assert captured["config"]["output"] == "minimal"
