"""Regression tests for coherent CLI session identity (Issue #3133).

The `session` sub-commands previously split across two independent stores:
`list`/`resume`/`--continue` read the project-scoped + global
``DefaultSessionStore`` (JSON message files) while `show`/`delete`/`export`
read a second ``SessionManager`` (dir-per-session). An id resumable via one
path was invisible to the other.

These tests assert the invariant: any id returned by ``session list`` /
resolvable by resume is also ``show``-able, ``export``-able and
``delete``-able through the shared resolver.
"""

import os
from pathlib import Path

import pytest

from praisonaiagents.session.store import DefaultSessionStore


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Run inside an isolated project dir with an isolated sessions home."""
    monkeypatch.chdir(tmp_path)
    # Point the core sessions home at a temp dir so project + global stores
    # both resolve under this test's sandbox.
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praison_home"))
    import praisonaiagents.paths as _paths

    sessions_dir = tmp_path / "sessions"

    def _fake_get_sessions_dir():
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    monkeypatch.setattr(_paths, "get_sessions_dir", _fake_get_sessions_dir)
    monkeypatch.setattr(
        "praisonaiagents.session.store.get_sessions_dir", _fake_get_sessions_dir
    )
    return tmp_path


def _create_project_session(session_id: str, project_path=None) -> None:
    """Create a session in the canonical project store used by list/resume."""
    from praisonai_code.cli.state.project_sessions import get_project_session_store

    store = get_project_session_store(project_path)
    store.add_message(session_id, "user", "hello")
    store.add_message(session_id, "assistant", "hi there")
    store.update_session_metadata(session_id, agent_name="Tester", model="gpt-4o")


def test_project_session_is_resolvable(project):
    """A session in the project store resolves via the shared resolver."""
    from praisonai_code.cli.state.session_resolver import resolve_session

    _create_project_session("sess-resolve")
    resolved = resolve_session("sess-resolve")

    assert resolved.found is True
    assert resolved.session_id == "sess-resolve"
    assert resolved.agent_name == "Tester"
    assert resolved.model == "gpt-4o"
    assert resolved.message_count == 2


def test_listed_session_is_show_export_delete_able(project):
    """The core invariant: anything listable is show/export/delete-able.

    Every id ``list_project_sessions`` returns must resolve (show), export, and
    delete through the shared resolver.
    """
    from praisonai_code.cli.state.project_sessions import list_project_sessions
    from praisonai_code.cli.state.session_resolver import (
        delete_session,
        export_session,
        resolve_session,
    )

    _create_project_session("sess-a")
    _create_project_session("sess-b")

    listed = list_project_sessions()
    ids = {s.get("session_id") for s in listed}
    assert {"sess-a", "sess-b"} <= ids

    for sid in ("sess-a", "sess-b"):
        assert resolve_session(sid).found is True, f"{sid} not show-able"
        assert export_session(sid, format="md") is not None, f"{sid} not export-able"

    assert delete_session("sess-a") is True
    # Deleted id no longer resolves; the other remains coherent.
    assert resolve_session("sess-a").found is False
    assert resolve_session("sess-b").found is True


def test_resumable_session_is_showable(project):
    """A session resumable via rehydrate is show-able by the same id."""
    from praisonai_code.cli.session.resume import rehydrate_session
    from praisonai_code.cli.state.session_resolver import resolve_session

    _create_project_session("sess-resume")

    restored = rehydrate_session("sess-resume")
    assert restored.found is True

    resolved = resolve_session("sess-resume")
    assert resolved.found is True
    assert resolved.session_id == restored.session_id


def test_export_json_roundtrip(project):
    """JSON export surfaces the resolved session id and history."""
    import json

    from praisonai_code.cli.state.session_resolver import export_session

    _create_project_session("sess-json")
    content = export_session("sess-json", format="json")
    assert content is not None
    data = json.loads(content)
    assert data["session_id"] == "sess-json"
    assert data["found"] is True
    assert len(data["chat_history"]) == 2


def test_missing_session_not_found(project):
    """An unknown id resolves to not-found across all operations."""
    from praisonai_code.cli.state.session_resolver import (
        delete_session,
        export_session,
        resolve_session,
    )

    assert resolve_session("nope").found is False
    assert export_session("nope") is None
    assert delete_session("nope") is False


def test_cli_show_delete_export_on_listed_session(project):
    """End-to-end: `session show/export/delete` succeed for a listed id.

    Mirrors the real workflow — create a session (as `run`/`--continue` would),
    then drive the actual Typer sub-commands so `show`/`export`/`delete`
    resolve exactly that id (Issue #3133).
    """
    from typer.testing import CliRunner

    from praisonai_code.cli.commands.session import app

    _create_project_session("sess-cli")
    runner = CliRunner()

    show = runner.invoke(app, ["show", "sess-cli"])
    assert show.exit_code == 0, show.output

    export = runner.invoke(app, ["export", "sess-cli", "--format", "md"])
    assert export.exit_code == 0, export.output

    delete = runner.invoke(app, ["delete", "sess-cli", "--yes"])
    assert delete.exit_code == 0, delete.output

    # After deletion it is gone from show too.
    gone = runner.invoke(app, ["show", "sess-cli"])
    assert gone.exit_code == 1


def test_legacy_session_manager_fallback(project, monkeypatch):
    """Pre-existing SessionManager sessions remain manageable during deprecation."""
    from praisonai_code.cli.state import sessions as sessions_mod
    from praisonai_code.cli.state.identifiers import RunContext
    from praisonai_code.cli.state.session_resolver import (
        delete_session,
        resolve_session,
    )

    legacy_dir = project / "legacy_sessions"
    manager = sessions_mod.SessionManager(sessions_dir=legacy_dir)
    monkeypatch.setattr(sessions_mod, "_session_manager", manager)

    ctx = RunContext(run_id="legacy-1", trace_id="t", workspace=str(project))
    manager.create(ctx, name="Legacy")

    resolved = resolve_session("legacy-1")
    assert resolved.found is True
    assert resolved.agent_name == "Legacy"

    assert delete_session("legacy-1") is True
    assert resolve_session("legacy-1").found is False


def test_delete_reports_store_failure(project, monkeypatch):
    """A store I/O failure on delete is not reported as success (Issue #3133)."""
    from praisonai_code.cli.state import session_resolver
    from praisonai_code.cli.state.session_resolver import delete_session

    class _FailingStore:
        def delete_session(self, session_id):
            return False

    # The owning store confirms *no* removal (its delete_session returns False)
    # and there is no legacy record, so nothing was actually deleted.
    monkeypatch.setattr(session_resolver, "_store_for", lambda *a, **k: _FailingStore())
    monkeypatch.setattr(session_resolver, "_legacy_delete", lambda sid: False)

    assert delete_session("sess-fail") is False


def test_delete_sweeps_legacy_duplicate(project, monkeypatch):
    """A duplicate legacy record is swept even when a canonical record exists.

    Prevents a session the CLI reported as deleted from reappearing via the
    legacy fallback on the next resolve (Issue #3133 zombie sessions).
    """
    from praisonai_code.cli.state import sessions as sessions_mod
    from praisonai_code.cli.state.identifiers import RunContext
    from praisonai_code.cli.state.session_resolver import (
        delete_session,
        resolve_session,
    )

    # Same id lives in both the canonical project store and the legacy store.
    _create_project_session("dup-id")

    legacy_dir = project / "legacy_sessions"
    manager = sessions_mod.SessionManager(sessions_dir=legacy_dir)
    monkeypatch.setattr(sessions_mod, "_session_manager", manager)
    ctx = RunContext(run_id="dup-id", trace_id="t", workspace=str(project))
    manager.create(ctx, name="LegacyDup")

    assert delete_session("dup-id") is True
    # Neither the canonical nor the legacy record survives.
    assert resolve_session("dup-id").found is False


def test_read_failure_does_not_leak_other_session(project, monkeypatch):
    """A read failure on the owning store reports not-found, not another record.

    ``show``/``export`` must not silently return a different same-id session
    from another store when the resolved store cannot read its record.
    """
    from praisonai_code.cli.state import session_resolver
    from praisonai_code.cli.state.session_resolver import resolve_session

    class _FailingReadStore:
        def get_session(self, session_id):
            raise IOError("simulated read failure")

    # The owning store is located but cannot read the record. resolve must
    # report not-found for this record, not fall through to legacy.
    monkeypatch.setattr(
        session_resolver, "_store_for", lambda *a, **k: _FailingReadStore()
    )
    called = {"legacy": False}

    def _spy_legacy(sid):
        called["legacy"] = True
        return None

    monkeypatch.setattr(session_resolver, "_legacy_get", _spy_legacy)

    assert resolve_session("sess-read").found is False
    # It must not have leaked through to the legacy fallback.
    assert called["legacy"] is False
