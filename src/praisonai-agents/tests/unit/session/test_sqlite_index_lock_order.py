"""Index refresh follows durable generations without blocking unrelated queries."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import praisonaiagents.session.sqlite_store as sqlite_module
import praisonaiagents.session.store as store_module
from praisonaiagents.session.sqlite_store import SqliteSessionStore
from praisonaiagents.session.store import DefaultSessionStore, FileLock, SessionData, SessionMessage


@pytest.fixture
def store(tmp_path):
    result = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    assert result.add_message("busy", "user", "old pelican")
    assert result.add_message("other", "user", "other narwhal")
    assert result.set_gateway_info("other", gateway_session_id="other-gateway")
    assert result.get_by_gateway_session("other-gateway") is not None
    yield result
    if result._conn is not None:
        result._conn.close()


@pytest.mark.parametrize("operation", ["refresh", "delete", "backfill"])
def test_contended_file_does_not_hold_database_lock(store, monkeypatch, operation):
    """Observe the real file-lock wait while another index query completes."""
    snapshot = store.get_session("busy")
    filepath = store._get_session_path("busy")
    waiting = threading.Event()

    class ObservedLock(FileLock):
        def __enter__(self):
            if self.filepath == filepath:
                waiting.set()
            return super().__enter__()

    held = FileLock(filepath, store.lock_timeout)
    held.__enter__()
    monkeypatch.setattr(sqlite_module, "FileLock", ObservedLock)
    monkeypatch.setattr(store_module, "FileLock", ObservedLock)
    if operation == "backfill":
        store._backfilled = False
        store._deindex_session("busy")
    with ThreadPoolExecutor(max_workers=2) as executor:
        try:
            if operation == "refresh":
                worker = executor.submit(store._index_session, snapshot)
            elif operation == "delete":
                worker = executor.submit(store.delete_session, "busy")
            else:
                worker = executor.submit(store._ensure_backfilled)
            assert waiting.wait(2), "worker did not reach file-lock acquisition"
            if operation == "backfill":
                assert "other" in executor.submit(store._indexed_ids).result(timeout=1)
            else:
                result = executor.submit(store.get_by_gateway_session, "other-gateway").result(timeout=1)
                assert result.session_id == "other"
        finally:
            held.__exit__(None, None, None)
        worker.result(timeout=5)


def test_stale_refresh_indexes_recreated_session_generation(store):
    """A snapshot captured before deletion must not overwrite the new index."""
    assert store.set_gateway_info("busy", gateway_session_id="old-route", agent_id="old-agent")
    stale = store.get_session("busy")
    assert store.delete_session("busy")
    replacement = SessionData(session_id="busy", gateway_session_id="new-route", agent_id="new-agent")
    replacement.messages = [SessionMessage(role="user", content="new narwhal")]
    plain = DefaultSessionStore(session_dir=store.session_dir)
    assert plain._save_session(replacement)
    store._index_session(stale)
    conn = store._connect()
    assert conn.execute("SELECT content FROM session_fts WHERE session_id = ?", ("busy",)).fetchone()[0] == "new narwhal"
    assert conn.execute("SELECT gateway_session_id, agent_id FROM session_route WHERE session_id = ?", ("busy",)).fetchone() == ("new-route", "new-agent")
    assert conn.execute("SELECT updated_at FROM session_meta WHERE session_id = ?", ("busy",)).fetchone()[0] == replacement.updated_at


def test_corruption_callback_can_query_during_backfill(store, monkeypatch):
    from pathlib import Path

    Path(store._get_session_path("broken")).write_text("{invalid", encoding="utf-8")
    store._backfilled = False
    callbacks, failures = [], []

    def on_corruption(*args):
        callbacks.append((store.get_by_gateway_session("other-gateway").session_id,
                          [hit.session_id for hit in store.search("narwhal")]))

    monkeypatch.setattr(store, "_fire_corruption_hook", on_corruption)

    def backfill():
        try:
            store._ensure_backfilled()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=backfill, daemon=True)
    worker.start()
    worker.join(2)
    assert not worker.is_alive(), "corruption callback deadlocked during backfill"
    assert failures == []
    assert callbacks == [("other", ["other"])]
    assert store._backfilled


def test_failed_backfill_can_retry(store, monkeypatch):
    store._backfilled = False
    original = store._reindex_all

    def fail():
        raise RuntimeError("backfill failed")

    monkeypatch.setattr(store, "_reindex_all", fail)
    with pytest.raises(RuntimeError, match="backfill failed"):
        store._ensure_backfilled()
    assert not store._backfilled
    monkeypatch.setattr(store, "_reindex_all", original)
    store._ensure_backfilled()
    assert store._backfilled
