"""Unreadable transcript bytes must not interrupt recall of valid sessions."""

import pytest

from praisonaiagents.session import SqliteSessionStore
from praisonaiagents.session.store import DefaultSessionStore


@pytest.mark.parametrize("backend", ["json", "fts", "like"])
def test_search_skips_invalid_utf8_candidate(tmp_path, backend):
    store = (
        DefaultSessionStore(session_dir=str(tmp_path))
        if backend == "json"
        else SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    )
    try:
        assert store.add_message("bad", "user", "migration needle")
        assert store.add_message("valid", "user", "migration needle")
        if backend == "fts" and not store._fts_available:
            pytest.skip("SQLite build lacks FTS5")
        if backend == "like":
            store._fts_available = False
        assert {hit.session_id for hit in store.search("needle")} == {"bad", "valid"}
        bad = tmp_path / "bad.json"
        payload = b"\xff\xfe"
        bad.write_bytes(payload)
        hits = store.search("needle")
        assert [hit.session_id for hit in hits] == ["valid"]
        assert hits[0].messages[0]["content"] == "migration needle"
        assert bad.read_bytes() == payload
    finally:
        conn = getattr(store, "_conn", None)
        if conn is not None:
            conn.close()
