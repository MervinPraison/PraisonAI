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
    # ``DEFAULT_SESSION_DIR`` is served lazily via a module ``__getattr__`` and
    # is not a real attribute, so ``monkeypatch.setattr`` would mistake the
    # computed value for the "original" and restore it as a real global on
    # teardown (leaking the override into later tests). Manage the real global
    # directly and delete it in a finally instead.
    store_module.DEFAULT_SESSION_DIR = str(tmp_path / "pinned")
    try:
        assert (
            store_module.DefaultSessionStore().session_dir
            == str(tmp_path / "pinned")
        )
    finally:
        del store_module.DEFAULT_SESSION_DIR


def test_injected_default_store_is_never_replaced(tmp_path, monkeypatch):
    """A store injected by a caller is honoured verbatim."""
    injected = store_module.DefaultSessionStore(session_dir=str(tmp_path / "x"))
    monkeypatch.setattr(store_module, "_default_store", injected, raising=False)

    assert store_module.get_default_session_store() is injected


def test_restored_autocreated_store_still_follows_the_dir(tmp_path, monkeypatch):
    """A partial teardown that restores only ``_default_store`` must not pin it.

    A test/embedding may save the auto-created singleton, reset it to ``None``,
    rebuild a different one via ``get_default_session_store()``, then restore
    the original ``_default_store`` without touching any out-of-band tracking
    state. The restored store must still be recognised as auto-created and
    rebuilt on the next directory change -- not misclassified as caller-injected
    and pinned to a stale directory (regression for the identity-tracking gap).
    """
    monkeypatch.setattr(store_module, "_default_store", None, raising=False)

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "a"))
    original = store_module.get_default_session_store()
    assert original.session_dir == str(tmp_path / "a" / "sessions")

    # A helper rebuilds a *different* auto-created store, then teardown restores
    # only the original singleton reference.
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "temp"))
    store_module._default_store = None
    store_module.get_default_session_store()
    store_module._default_store = original

    # The restored store is still recognised as auto-created and follows the
    # resolved directory when it changes.
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "b"))
    rebuilt = store_module.get_default_session_store()
    assert rebuilt is not original
    assert rebuilt.session_dir == str(tmp_path / "b" / "sessions")
