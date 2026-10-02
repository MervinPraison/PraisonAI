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


@pytest.mark.parametrize("backend", ["fts", "like"])
def test_unreadable_candidates_do_not_hide_later_valid_hit(tmp_path, backend):
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    try:
        for index in range(25):
            assert store.add_message(f"bad{index:02}", "user", "needle")
        assert store.add_message("valid", "user", "needle " + "filler " * 100)
        if backend == "fts" and not store._fts_available:
            pytest.skip("SQLite build lacks FTS5")
        if backend == "like":
            store._fts_available = False
        store._ensure_backfilled()
        candidates = store._candidate_ids("needle", 5)
        assert len(candidates) == 25 and "valid" not in candidates
        for index in range(25):
            (tmp_path / f"bad{index:02}.json").write_bytes(b"\xff\xfe")
        assert [hit.session_id for hit in store.search("needle")] == ["valid"]
    finally:
        if store._conn is not None:
            store._conn.close()


@pytest.mark.parametrize("backend", ["json", "fts"])
def test_search_reports_corruption_without_moving_file(tmp_path, monkeypatch, caplog, backend):
    store = DefaultSessionStore(session_dir=str(tmp_path)) if backend == "json" else SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    events = []
    monkeypatch.setattr(store, "_fire_corruption_hook", lambda *args: events.append(args))
    try:
        assert store.add_message("bad", "user", "needle")
        assert store.add_message("valid", "user", "needle")
        store.search("needle")
        bad = tmp_path / "bad.json"
        bad.write_bytes(b"\xff\xfe")
        assert [hit.session_id for hit in store.search("needle")] == ["valid"]
        assert events and events[0][0] == "bad" and events[0][2] is None
        assert "Skipping unreadable session file" in caplog.text
        assert bad.read_bytes() == b"\xff\xfe"
    finally:
        conn = getattr(store, "_conn", None)
        if conn is not None:
            conn.close()


@pytest.mark.parametrize("backend", ["fts", "like"])
def test_broad_query_stops_loading_after_readable_allowance(tmp_path, monkeypatch, backend):
    import builtins

    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    try:
        for index in range(60):
            assert store.add_message(f"s{index:02}", "user", "needle")
        if backend == "like":
            store._fts_available = False
        store._ensure_backfilled()
        opened = []
        original = builtins.open

        def tracked(path, *args, **kwargs):
            if str(path).endswith(".json"):
                opened.append(str(path))
            return original(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", tracked)
        assert len(store.search("needle", limit=5)) == 5
        assert len(opened) == 25
    finally:
        store._conn.close()


@pytest.mark.parametrize("backend", ["fts", "like"])
def test_index_deletion_during_read_does_not_shift_candidates(tmp_path, backend):
    store = SqliteSessionStore(session_dir=str(tmp_path))
    peer = SqliteSessionStore(session_dir=str(tmp_path))
    try:
        for index in range(25):
            assert store.add_message(f"bad{index:02}", "user", "needle")
        assert store.add_message("valid", "user", "needle " + "filler " * 100)
        if backend == "like":
            store._fts_available = False
        store._ensure_backfilled()
        peer_conn = peer._connect()
        for index in range(25):
            (tmp_path / f"bad{index:02}.json").write_bytes(b"\xff\xfe")
        conn = store._conn
        changed = []

        def change_index():
            if not changed:
                peer_conn.execute("DELETE FROM session_fts WHERE session_id = ?", ("bad00",))
                changed.append(True)

        class Cursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def fetchall(self):
                rows = self.cursor.fetchall()
                change_index()
                return rows

            def fetchone(self):
                row = self.cursor.fetchone()
                change_index()
                return row

            def close(self):
                self.cursor.close()

        class Connection:
            def execute(self, sql, params=()):
                return Cursor(conn.execute(sql, params))

            def close(self):
                conn.close()

        store._conn = Connection()
        assert [hit.session_id for hit in store.search("needle")] == ["valid"]
        assert changed
    finally:
        for current in (store, peer):
            if current._conn is not None:
                current._conn.close()


@pytest.mark.parametrize("operation", ["list", "agent", "gateway", "gateway_agent", "export_all", "lineage"])
def test_directory_reads_skip_invalid_utf8(tmp_path, monkeypatch, operation):
    import praisonaiagents.session.store as module

    store = DefaultSessionStore(session_dir=str(tmp_path))
    assert store.add_message("valid", "user", "durable history")
    assert store.set_agent_info("valid", agent_name="support")
    assert store.set_gateway_info("valid", gateway_session_id="gateway", agent_id="agent")
    assert store.update_session_metadata("valid", lineage_id="thread")
    bad = tmp_path / "bad.json"
    payload = b"\xff\xfe"
    bad.write_bytes(payload)
    original = module.os.listdir
    monkeypatch.setattr(module.os, "listdir", lambda path: [bad.name, "valid.json"] if str(path) == str(tmp_path) else original(path))

    if operation == "list":
        assert [row["session_id"] for row in store.list_sessions()] == ["valid"]
    elif operation == "agent":
        assert store.list_sessions_by_agent("support") == ["valid"]
    elif operation == "gateway":
        assert store.get_by_gateway_session("gateway").session_id == "valid"
    elif operation == "gateway_agent":
        assert store.list_sessions_by_gateway_agent("agent") == ["valid"]
    else:
        exported = store.export_all() if operation == "export_all" else store.export_session("valid")
        assert [row["session_id"] for row in exported["sessions"]] == ["valid"]
        assert exported["sessions"][0]["messages"][0]["content"] == "durable history"
    assert bad.read_bytes() == payload
