"""Issue #6284: a requested-but-failed resume on the bare launch must warn."""

from typer.testing import CliRunner

import praisonai_code._wrapper_bridge as bridge
import praisonai_code.cli.interactive.async_tui as async_tui
import praisonai_code.cli.state.project_sessions as project_sessions
from praisonai_code.cli.app import app


class _FakeTUI:
    last_config = None

    def __init__(self, config):
        _FakeTUI.last_config = config

    def run(self):
        pass


def _patch_launch(monkeypatch):
    monkeypatch.setattr(bridge, "wrapper_available", lambda: False)
    monkeypatch.setattr(async_tui, "AsyncTUI", _FakeTUI)
    monkeypatch.setenv("PRAISONAI_NO_UPDATE_CHECK", "1")
    _FakeTUI.last_config = None


def test_failed_session_resume_warns_and_starts_fresh(monkeypatch):
    _patch_launch(monkeypatch)

    def _boom(_sid):
        raise RuntimeError("store corrupted")

    monkeypatch.setattr(project_sessions, "session_exists_anywhere", _boom)

    result = CliRunner().invoke(app, ["--session", "abc123"])

    assert result.exit_code == 0, result.output
    assert "could not resume session abc123" in result.output
    assert "store corrupted" in result.output
    assert "Starting a new session" in result.output
    assert _FakeTUI.last_config.session_id is None
    assert _FakeTUI.last_config.resume is False


def test_failed_continue_warns(monkeypatch):
    _patch_launch(monkeypatch)

    def _boom(*_a, **_k):
        raise RuntimeError("db locked")

    monkeypatch.setattr(project_sessions, "find_last_session", _boom)

    result = CliRunner().invoke(app, ["--continue"])

    assert result.exit_code == 0, result.output
    assert "could not resume session last session" in result.output
    assert "db locked" in result.output
    assert _FakeTUI.last_config.resume is False


def test_successful_resume_is_silent(monkeypatch):
    _patch_launch(monkeypatch)
    monkeypatch.setattr(project_sessions, "session_exists_anywhere", lambda s: True)
    monkeypatch.setattr(project_sessions, "find_session_model", lambda s: None)

    result = CliRunner().invoke(app, ["--session", "abc123"])

    assert result.exit_code == 0, result.output
    assert "could not resume" not in result.output
    assert _FakeTUI.last_config.session_id == "abc123"
    assert _FakeTUI.last_config.resume is True
