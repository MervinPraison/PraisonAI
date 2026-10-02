"""Default imports must not overwrite a session created after the first check."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_store import SqliteSessionStore


@pytest.mark.parametrize("overwrite", [False, True])
@pytest.mark.parametrize("kind", [DefaultSessionStore, SqliteSessionStore])
def test_import_rechecks_new_peer_session_under_write_lock(tmp_path, monkeypatch, overwrite, kind):
    directory = str(tmp_path / "sessions")
    importer = kind(session_dir=directory, **({"db_path": ":memory:"} if kind is SqliteSessionStore else {}))
    peer = DefaultSessionStore(session_dir=directory)
    ready, completed = Event(), Event()
    original = importer._save_imported_session

    def pause_before_write(*args, **kwargs):
        ready.set()
        assert completed.wait(10), "peer did not finish creating its session"
        return original(*args, **kwargs)

    monkeypatch.setattr(importer, "_save_imported_session", pause_before_write)
    payload = {"version": 1, "sessions": [{
        "session_id": "shared", "messages": [{
            "role": "user", "content": "imported", "timestamp": 1,
        }],
    }]}

    def create_peer():
        assert ready.wait(10), "import did not reach write boundary"
        try:
            assert peer.add_message("shared", "user", "peer-created")
        finally:
            completed.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(create_peer)
        report = importer.import_sessions(payload, overwrite=overwrite)
        future.result(timeout=15)
    fresh = DefaultSessionStore(session_dir=directory)
    if overwrite:
        assert report.imported == 1
        assert not report.skipped
        assert fresh.get_chat_history("shared") == [{"role": "user", "content": "imported"}]
    else:
        assert report.imported == 0
        assert report.skipped == [{
            "session_id": "shared", "reason": "already exists (use overwrite)",
        }]
        assert fresh.get_chat_history("shared") == [{"role": "user", "content": "peer-created"}]
    if kind is SqliteSessionStore and importer._conn is not None:
        importer._conn.close()
