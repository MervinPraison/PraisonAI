"""Backfill callbacks may query the same indexed store without restarting a pass."""

import threading

import pytest

from praisonaiagents.session.sqlite_store import SqliteSessionStore


@pytest.mark.parametrize("query", ["route", "search"])
def test_corruption_callback_can_query_same_store(tmp_path, monkeypatch, query):
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    assert store.add_message("healthy", "user", "narwhal record")
    assert store.set_gateway_info("healthy", gateway_session_id="gateway")
    assert store.get_by_gateway_session("gateway") is not None
    (tmp_path / "broken.json").write_text("{invalid", encoding="utf-8")
    store._backfilled = False
    results, failures = [], []

    def on_corruption(*args):
        if query == "route":
            results.append(store.get_by_gateway_session("gateway").session_id)
        else:
            results.append([hit.session_id for hit in store.search("narwhal")])

    monkeypatch.setattr(store, "_fire_corruption_hook", on_corruption)

    def backfill():
        try:
            store._ensure_backfilled()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=backfill, daemon=True)
    worker.start()
    worker.join(2)
    try:
        assert not worker.is_alive(), "callback query deadlocked during backfill"
        assert failures == []
        expected = ["healthy"] if query == "route" else [["healthy"]]
        assert results == expected
        assert store._backfilled
    finally:
        if not worker.is_alive() and store._conn is not None:
            store._conn.close()


def test_raised_backfill_releases_running_guard_for_retry(tmp_path, monkeypatch):
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    original = store._reindex_all

    def fail():
        raise RuntimeError("failed pass")

    monkeypatch.setattr(store, "_reindex_all", fail)
    try:
        with pytest.raises(RuntimeError, match="failed pass"):
            store._ensure_backfilled()
        assert not store._backfilled
        monkeypatch.setattr(store, "_reindex_all", original)
        store._ensure_backfilled()
        assert store._backfilled
    finally:
        if store._conn is not None:
            store._conn.close()
