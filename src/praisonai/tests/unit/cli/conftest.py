"""Shared fixtures for CLI unit tests."""

import pytest

import praisonai.cli.state.project_sessions as project_sessions
from praisonaiagents.session.store import DefaultSessionStore


@pytest.fixture(autouse=True)
def isolated_session_stores(request, monkeypatch, tmp_path):
    """Keep session I/O off shared dirs when pytest-xdist runs workers in parallel."""
    if request.node.get_closest_marker("no_session_isolation"):
        # Tests that opt out must NOT also explicitly request this fixture as a
        # parameter, because they would receive None and fail to unpack it.
        # ``fixturenames`` always contains this autouse fixture, so inspect the
        # test function's own signature to detect an *explicit* request.
        test_fn = getattr(request.node, "function", None)
        code = getattr(test_fn, "__code__", None)
        arg_count = getattr(code, "co_argcount", 0)
        explicit_args = getattr(code, "co_varnames", ())[:arg_count]
        if "isolated_session_stores" in explicit_args:
            raise pytest.UsageError(
                f"{request.node.name}: 'no_session_isolation' marker cannot be "
                "combined with an explicit 'isolated_session_stores' fixture parameter."
            )
        return None

    import praisonaiagents.session.store as store_mod

    base = tmp_path / "session-isolation"
    # Redirect the project-scoped store to a temp dir while still exercising the
    # real ProjectSessionStore class (so project_id/project_name/get_last_session_id
    # remain testable). Falls back to DefaultSessionStore if the project variant
    # is unavailable for any reason.
    project_dir = base / "project"
    monkeypatch.setattr(
        project_sessions, "get_project_sessions_dir", lambda *a, **k: project_dir
    )
    project_store_cls = getattr(project_sessions, "ProjectSessionStore", None)
    if project_store_cls is not None:
        project_store = project_store_cls()
    else:
        project_store = DefaultSessionStore(session_dir=str(project_dir))
    global_store = DefaultSessionStore(session_dir=str(base / "global"))
    monkeypatch.setattr(
        project_sessions, "get_project_session_store", lambda *a, **k: project_store
    )
    monkeypatch.setattr(project_sessions, "_get_default_store", lambda: global_store)
    monkeypatch.setattr(store_mod, "get_default_session_store", lambda: global_store)
    monkeypatch.setattr(store_mod, "_default_store", global_store, raising=False)
    return project_store, global_store
