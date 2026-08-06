"""
Regression tests for the wrapper TUI's /diff and /undo commands.

These were previously dead stubs that only printed "use git diff" help text.
They must now be wired to the same SessionCheckpointManager engine the legacy
REPL uses, so a user gets real session file changes and rollbacks from the TUI.
"""

import asyncio
import os
import tempfile

import pytest

pytest.importorskip("textual")

from praisonai.cli.features.tui import app as tui_app


class _FakeScreen:
    """Stand-in main screen that records assistant messages."""

    def __init__(self):
        self.messages = []

    async def add_assistant_message(self, content, agent_name=None):
        self.messages.append(content)


class _StubApp:
    """Minimal carrier so we can drive the TUIApp command methods directly."""

    # Bind the real (unbound) methods under test onto a lightweight object,
    # avoiding a full Textual App bring-up.
    _cmd_diff = tui_app.TUIApp._cmd_diff
    _cmd_undo = tui_app.TUIApp._cmd_undo
    _get_session_checkpoints = tui_app.TUIApp._get_session_checkpoints

    def __init__(self, workspace, screen):
        self.workspace = workspace
        self.screen = screen


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _write(path, content):
    with open(path, "w") as f:
        f.write(content)


def test_tui_diff_undo_functional(monkeypatch):
    """TUI /diff reports real session changes and /undo rolls files back."""
    monkeypatch.setenv("PRAISONAI_CHECKPOINTS", "on")
    with tempfile.TemporaryDirectory() as workspace:
        # Make the fake screen pass the isinstance(screen, MainScreen) gate.
        screen = _FakeScreen()
        monkeypatch.setattr(tui_app, "MainScreen", _FakeScreen)

        target = os.path.join(workspace, "mod.py")
        _write(target, "v0\n")

        app = _StubApp(workspace=workspace, screen=screen)

        # First call builds the manager and takes a session-start baseline.
        ckpt = app._get_session_checkpoints()
        assert ckpt is not None and ckpt.enabled is True

        # Agent edits the file this session.
        _write(target, "v0\nv1\n")

        # /diff surfaces the change (not a "use git diff" stub).
        _run(app._cmd_diff(""))
        assert screen.messages, "diff should push a message"
        diff_msg = screen.messages[-1]
        assert "mod.py" in diff_msg
        assert "git diff" not in diff_msg.lower()

        # /undo rolls the workspace file back to the baseline.
        _run(app._cmd_undo(""))
        with open(target) as f:
            assert f.read() == "v0\n"


def test_tui_diff_disabled_reports_enable_hint(monkeypatch):
    """With checkpointing off, /diff explains how to enable, not a git stub."""
    monkeypatch.setenv("PRAISONAI_CHECKPOINTS", "off")
    with tempfile.TemporaryDirectory() as workspace:
        screen = _FakeScreen()
        monkeypatch.setattr(tui_app, "MainScreen", _FakeScreen)
        app = _StubApp(workspace=workspace, screen=screen)

        _run(app._cmd_diff(""))
        assert screen.messages
        msg = screen.messages[-1].lower()
        assert "checkpointing is disabled" in msg
        assert "praisonai_checkpoints" in msg or "checkpoints.auto" in msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
