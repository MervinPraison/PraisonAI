"""Independent WAL readers must never observe half an index replacement."""

import sqlite3
import threading

import pytest

from praisonaiagents.session import SqliteSessionStore


@pytest.mark.parametrize("failure", [False, True])
def test_wal_reader_retains_session_during_or_after_failed_index_refresh(tmp_path, monkeypatch, failure):
    store = SqliteSessionStore(session_dir=str(tmp_path))
    deleted = threading.Event()
    resume = threading.Event()
    worker = None
    reader = None
    try:
        assert store.add_message("session", "user", "needle old")
        conn = store._conn
        session = store._read_session_fresh("session")
        session.messages[0].content = "needle new"
        reader = sqlite3.connect(store.db_path, isolation_level=None)

        class PausedConnection:
            def execute(self, sql, parameters=()):
                if failure and sql.startswith("INSERT INTO session_fts"):
                    raise sqlite3.OperationalError("injected index insert failure")
                result = conn.execute(sql, parameters)
                if sql.startswith("DELETE FROM session_fts"):
                    deleted.set()
                    if not resume.wait(5):
                        raise TimeoutError("reader did not resume index writer")
                return result

        monkeypatch.setattr(store, "_connect", lambda: PausedConnection())
        worker = threading.Thread(target=store._index_session, args=(session,))
        worker.start()
        assert deleted.wait(5)
        # This is a second real connection, outside the store's Python lock.
        during = reader.execute("SELECT content FROM session_fts WHERE session_id = ?", ("session",)).fetchall()
        resume.set()
        worker.join(5)
        assert not worker.is_alive()
        after = reader.execute("SELECT content FROM session_fts WHERE session_id = ?", ("session",)).fetchall()
        assert during == [("needle old",)]
        assert after == [("needle old" if failure else "needle new",)]
        assert not conn.in_transaction
    finally:
        resume.set()
        if worker is not None:
            worker.join(5)
        if reader is not None:
            reader.close()
        if store._conn is not None:
            store._conn.close()
