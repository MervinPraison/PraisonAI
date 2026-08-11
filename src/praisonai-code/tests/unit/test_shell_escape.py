"""Tests for the interactive ``!cmd`` shell escape (issue #3742).

The interactive REPL/TUI must let a user run a quick shell command with a
``!`` prefix, reusing the *same* gated executor (env gate, 30s timeout, 100KB
output cap) that already powers command-template ``!`cmd`` substitution — and
without consuming a model turn. ``!!cmd`` additionally attaches the output as
context for the next message.
"""

import os

import pytest

from praisonai_code.cli.features.custom_definitions import (
    SHELL_SUBSTITUTION_ENV,
    ShellEscapeResult,
    run_shell_escape,
    shell_escape_enabled,
)
from praisonai_code.cli.interactive.repl import InteractiveREPL
from praisonai_code.cli.interactive.tui_app import PraisonTUI


@pytest.fixture
def shell_on(monkeypatch):
    monkeypatch.setenv(SHELL_SUBSTITUTION_ENV, "true")


@pytest.fixture
def shell_off(monkeypatch):
    monkeypatch.delenv(SHELL_SUBSTITUTION_ENV, raising=False)
    # Neutralise the config fallback so the gate is deterministically off.
    monkeypatch.setattr(
        "praisonai_code.cli.features.custom_definitions._config_allows_shell",
        lambda: False,
    )


# ---------------------------------------------------------------------------
# Shared gated executor
# ---------------------------------------------------------------------------

def test_run_shell_escape_runs_and_captures_output(shell_on):
    result = run_shell_escape("echo hello-shell")
    assert result.enabled is True
    assert result.error is False
    assert result.output == "hello-shell"


def test_bang_gated_off_message(shell_off):
    result = run_shell_escape("echo hello")
    assert result.enabled is False
    assert not result.error
    assert SHELL_SUBSTITUTION_ENV in result.output
    assert not shell_escape_enabled()


def test_output_cap(shell_on):
    # Emit more than the 100KB cap; output must be truncated, not unbounded.
    result = run_shell_escape("yes x | head -c 200000")
    assert result.enabled is True
    assert len(result.output.encode()) <= 100_000


def test_timeout(shell_on, monkeypatch):
    monkeypatch.setattr(
        "praisonai_code.cli.features.custom_definitions.SHELL_SUBSTITUTION_TIMEOUT",
        1,
    )
    result = run_shell_escape("sleep 5")
    assert result.enabled is True
    assert result.error is True
    assert "timed out" in result.output.lower()


# ---------------------------------------------------------------------------
# REPL wiring
# ---------------------------------------------------------------------------

def test_repl_bang_runs_and_renders_without_model_call(shell_on):
    repl = InteractiveREPL()
    called = {"n": 0}
    repl._execute_prompt = lambda *a, **k: called.__setitem__("n", called["n"] + 1)

    infos = []
    repl.io.info = lambda msg: infos.append(msg)

    repl._handle_shell_escape("!echo repl-output")

    assert called["n"] == 0  # no model turn consumed
    assert any("repl-output" in m for m in infos)
    assert repl._pending_context == []


def test_repl_bang_gated_off_message(shell_off):
    repl = InteractiveREPL()
    infos = []
    repl.io.info = lambda msg: infos.append(msg)

    repl._handle_shell_escape("!echo hi")

    assert any(SHELL_SUBSTITUTION_ENV in m for m in infos)


def test_repl_double_bang_attaches_context(shell_on):
    repl = InteractiveREPL()
    repl.io.info = lambda msg: None
    repl.io.success = lambda msg: None

    repl._handle_shell_escape("!!echo attach-me")

    assert len(repl._pending_context) == 1
    assert "attach-me" in repl._pending_context[0]


def test_repl_double_bang_attaches_failed_output(shell_on):
    # A failed !!cmd still attaches its diagnostic output — the user explicitly
    # asked for it, so it must not be silently dropped.
    repl = InteractiveREPL()
    repl.io.info = lambda msg: None
    repl.io.tool_error = lambda msg: None
    repl.io.success = lambda msg: None

    repl._handle_shell_escape("!!sh -c 'echo boom >&2; exit 3'")

    assert len(repl._pending_context) == 1


def test_repl_pending_context_retained_on_model_failure(shell_on):
    # If the model call raises, explicitly attached context must survive so the
    # user can retry without re-running the command.
    repl = InteractiveREPL()
    repl.io.info = lambda msg: None
    repl.io.tool_error = lambda msg: None
    repl.io.success = lambda msg: None

    repl._handle_shell_escape("!!echo keep-me")
    assert len(repl._pending_context) == 1

    class _BoomAgent:
        def start(self, *a, **k):
            raise RuntimeError("model down")

    repl._agent = _BoomAgent()
    repl._execute_prompt("hello")

    assert len(repl._pending_context) == 1
    assert "keep-me" in repl._pending_context[0]


# ---------------------------------------------------------------------------
# TUI wiring
# ---------------------------------------------------------------------------

def test_tui_bang_runs_and_renders(shell_on):
    tui = PraisonTUI()
    tui._handle_shell_escape("!echo tui-output")

    system = [m.content for m in tui.messages if m.role == "system"]
    assert any("tui-output" in c for c in system)
    assert tui._pending_context == []


def test_tui_double_bang_attaches_context(shell_on):
    tui = PraisonTUI()
    tui._handle_shell_escape("!!echo tui-attach")

    assert len(tui._pending_context) == 1
    assert "tui-attach" in tui._pending_context[0]


def test_tui_pending_context_retained_on_model_failure(shell_on):
    tui = PraisonTUI()
    tui._handle_shell_escape("!!echo tui-keep")
    assert len(tui._pending_context) == 1

    class _BoomAgent:
        def start(self, *a, **k):
            raise RuntimeError("model down")

    tui._agent = _BoomAgent()
    tui._execute_prompt("hello")

    assert len(tui._pending_context) == 1
    assert "tui-keep" in tui._pending_context[0]
