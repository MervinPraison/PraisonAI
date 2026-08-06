"""Tests for `session fork` (Issue #3731).

`session fork <id>` forks an existing session into a new child session using the
same ``HierarchicalSessionStore.fork_session`` substrate that ``run --fork``
already relies on, recording parent/child lineage so both timelines stay
listable and resumable. These tests assert the fork is created against the real
canonical project store and that a missing session is a clean not-found.
"""

import pytest
import typer

from praisonai_code.cli.commands.session import session_fork


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Isolated project dir + sessions home under the test sandbox."""
    monkeypatch.chdir(tmp_path)
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


def _create_project_session(session_id: str) -> None:
    from praisonai_code.cli.state.project_sessions import get_project_session_store

    store = get_project_session_store()
    store.add_message(session_id, "user", "first")
    store.add_message(session_id, "assistant", "reply-1")
    store.add_message(session_id, "user", "second")
    store.add_message(session_id, "assistant", "reply-2")


def _forked_id(store, parent_id: str):
    """Return the single child id recorded on ``parent_id`` (or None)."""
    children = store.get_children(parent_id)
    return children[0] if children else None


def test_cli_session_fork(project, capsys):
    _create_project_session("sess-fork")

    session_fork("sess-fork", at_message=None, title="alt approach")

    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
    from praisonai_code.cli.utils.project import get_project_sessions_dir

    store = HierarchicalSessionStore(str(get_project_sessions_dir()))
    new_id = _forked_id(store, "sess-fork")

    assert new_id is not None
    assert store.get_parent(new_id) == "sess-fork"

    out = capsys.readouterr().out
    assert "sess-fork" in out
    assert new_id in out


def test_cli_session_fork_at_message_truncates(project):
    _create_project_session("sess-fork-at")

    session_fork("sess-fork-at", at_message=1, title=None)

    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
    from praisonai_code.cli.utils.project import get_project_sessions_dir

    store = HierarchicalSessionStore(str(get_project_sessions_dir()))
    new_id = _forked_id(store, "sess-fork-at")

    assert new_id is not None
    forked = store._load_extended_session(new_id, force_reload=True)
    # Only messages [0..1] copied when forking at index 1.
    assert len(forked.messages) == 2


def test_cli_session_fork_missing_is_clean_not_found(project):
    with pytest.raises(typer.Exit):
        session_fork("does-not-exist", at_message=None, title=None)
