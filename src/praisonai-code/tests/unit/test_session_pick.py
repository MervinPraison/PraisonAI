"""Tests for the interactive session picker (Issue #5164, PR #5214).

`_pick_session` powers `session resume` (no id on a TTY) and `run --pick`. These
tests exercise the selection front-end deterministically by stubbing the row
source (`list_project_sessions`) and the prompt (`IntPrompt.ask`) so no store or
real TTY is required. They pin the two review-hardened behaviours:

* cancelling / no sessions returns ``None`` (and `run --pick` then aborts rather
  than silently starting a fresh run — the P1 selection-gate regression);
* an unexpected *empty* store and a *failed* listing are distinguishable, so a
  storage error no longer masquerades as "No sessions found" (P2).
"""

import pytest

import praisonai_code.cli.commands.session as session_mod
from praisonai_code.cli.commands.session import _pick_session


class _Output:
    """Minimal output stub capturing the surfaces `_pick_session` touches."""

    def __init__(self):
        self.infos = []
        self.errors = []
        self.tables = []

    def print_info(self, msg):
        self.infos.append(msg)

    def print_error(self, msg, remediation=None):
        self.errors.append((msg, remediation))

    def print_table(self, headers, rows, title=None):
        self.tables.append((headers, rows, title))


def _stub_rows(monkeypatch, rows):
    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.list_project_sessions",
        lambda limit=20: rows,
    )


def _stub_prompt(monkeypatch, value):
    def _ask(*args, **kwargs):
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr("rich.prompt.IntPrompt.ask", staticmethod(_ask))


def test_pick_returns_selected_id(monkeypatch):
    _stub_rows(
        monkeypatch,
        [
            {"session_id": "sess-a", "title": "First", "message_count": 2},
            {"session_id": "sess-b", "title": "Second", "message_count": 5},
        ],
    )
    _stub_prompt(monkeypatch, 2)
    out = _Output()

    assert _pick_session(out) == "sess-b"
    assert out.tables, "picker should render a selection table"


def test_pick_cancel_returns_none(monkeypatch):
    _stub_rows(monkeypatch, [{"session_id": "sess-a", "title": "First"}])
    _stub_prompt(monkeypatch, 0)
    out = _Output()

    assert _pick_session(out) is None
    assert any("Cancel" in m for m in out.infos)


def test_pick_empty_store_reports_no_sessions(monkeypatch):
    _stub_rows(monkeypatch, [])
    out = _Output()

    assert _pick_session(out) is None
    assert out.infos == ["No sessions found"]
    assert not out.errors


def test_pick_listing_failure_surfaces_error_not_empty(monkeypatch):
    def _boom(limit=20):
        raise OSError("store unreadable")

    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.list_project_sessions", _boom
    )
    out = _Output()

    assert _pick_session(out) is None
    # A genuine failure must be an error (distinct from the empty-store info),
    # so users can tell "nothing to resume" apart from "listing broke".
    assert out.errors, "listing failure should surface as an error"
    assert "No sessions found" not in out.infos


def test_pick_unexpected_exception_propagates(monkeypatch):
    def _boom(limit=20):
        raise RuntimeError("unexpected regression")

    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.list_project_sessions", _boom
    )
    out = _Output()

    # Unexpected exceptions are not swallowed, preserving diagnostics.
    with pytest.raises(RuntimeError):
        _pick_session(out)


def test_resume_no_id_non_tty_still_requires_id(monkeypatch):
    """Non-TTY / --json `resume` with no id keeps the id-required error path.

    The picker must never fire off a TTY, so scripts and CI see today's
    behaviour unchanged.
    """
    import typer

    from praisonai_code.cli.commands.session import session_resume

    out = _Output()
    monkeypatch.setattr(session_mod, "get_output_controller", lambda: out)
    out.is_json_mode = False
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)

    # If the picker were (wrongly) invoked, this would flag it.
    def _should_not_run(_output):
        raise AssertionError("picker must not run in a non-TTY context")

    monkeypatch.setattr(session_mod, "_pick_session", _should_not_run)

    with pytest.raises(typer.Exit):
        session_resume(session_id=None, prompt=None, transcript=False)
    assert out.errors, "missing id must surface an error"


def test_resume_no_id_tty_uses_picker(monkeypatch):
    """On a TTY with no id, `resume` resolves the id via the picker."""
    from praisonai_code.cli.commands import session as sess

    out = _Output()
    out.is_json_mode = False
    monkeypatch.setattr(sess, "get_output_controller", lambda: out)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    monkeypatch.setattr(sess, "_pick_session", lambda output: "picked-id")

    captured = {}

    class _Restored:
        found = False

    def _fake_rehydrate(session_id):
        captured["session_id"] = session_id
        return _Restored()

    import praisonai_code.cli.session.resume as resume_mod

    monkeypatch.setattr(resume_mod, "rehydrate_session", _fake_rehydrate)

    import typer

    # Not found → Exit(1); we only assert the picked id reached rehydrate.
    with pytest.raises(typer.Exit):
        sess.session_resume(session_id=None, prompt=None, transcript=False)
    assert captured.get("session_id") == "picked-id"
