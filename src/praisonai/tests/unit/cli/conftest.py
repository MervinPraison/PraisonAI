"""Shared fixtures for CLI unit tests."""

import pytest

import praisonai.cli.state.project_sessions as project_sessions
from praisonaiagents.session.store import DefaultSessionStore


@pytest.fixture(autouse=True)
def isolated_session_stores(request, monkeypatch, tmp_path):
    """Keep session I/O off shared dirs when pytest-xdist runs workers in parallel."""
    if request.node.get_closest_marker("no_session_isolation"):
        return None

    import praisonaiagents.session.store as store_mod

    base = tmp_path / "session-isolation"
    project_store = DefaultSessionStore(session_dir=str(base / "project"))
    global_store = DefaultSessionStore(session_dir=str(base / "global"))
    monkeypatch.setattr(
        project_sessions, "get_project_session_store", lambda *a, **k: project_store
    )
    monkeypatch.setattr(project_sessions, "_get_default_store", lambda: global_store)
    monkeypatch.setattr(store_mod, "get_default_session_store", lambda: global_store)
    monkeypatch.setattr(store_mod, "_default_store", global_store, raising=False)
    return project_store, global_store
