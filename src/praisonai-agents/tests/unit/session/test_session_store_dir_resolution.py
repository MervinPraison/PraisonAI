"""The session store root must be resolved live, not frozen at import.

``DEFAULT_SESSION_DIR = str(get_sessions_dir())`` ran at module import, so any
later ``PRAISONAI_HOME`` override -- a container exporting it after the package
is imported, a test monkeypatching ``get_sessions_dir`` -- was ignored, and the
store kept reading, writing and deleting sessions in the wrong directory.
"""

import praisonaiagents.session.store as store_module


def test_default_session_dir_is_resolved_lazily(tmp_path, monkeypatch):
    """PRAISONAI_HOME set *after* import is honoured."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(store_module, "_default_store", None, raising=False)
    expected = str(tmp_path / "home" / "sessions")

    assert store_module.DEFAULT_SESSION_DIR == expected
    assert store_module.DefaultSessionStore().session_dir == expected
    assert store_module.get_default_session_store().session_dir == expected


def test_singleton_follows_the_resolved_dir(tmp_path, monkeypatch):
    """The cached singleton is rebuilt when the resolved directory changes."""
    monkeypatch.setattr(store_module, "_default_store", None, raising=False)

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "a"))
    first = store_module.get_default_session_store()
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "b"))
    second = store_module.get_default_session_store()

    assert first.session_dir == str(tmp_path / "a" / "sessions")
    assert second.session_dir == str(tmp_path / "b" / "sessions")
    assert first is not second


def test_explicit_module_override_still_wins(tmp_path, monkeypatch):
    """Assigning DEFAULT_SESSION_DIR keeps working for existing callers."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(store_module, "_default_store", None, raising=False)
    monkeypatch.setattr(
        store_module, "DEFAULT_SESSION_DIR", str(tmp_path / "pinned"), raising=False
    )

    assert store_module.DefaultSessionStore().session_dir == str(tmp_path / "pinned")


def test_injected_default_store_is_never_replaced(tmp_path, monkeypatch):
    """A store injected by a caller is honoured verbatim."""
    injected = store_module.DefaultSessionStore(session_dir=str(tmp_path / "x"))
    monkeypatch.setattr(store_module, "_default_store", injected, raising=False)

    assert store_module.get_default_session_store() is injected
