"""Route verification must not skip candidates after a concurrent deletion."""

import json
import sqlite3

import pytest

from praisonaiagents.session import SqliteSessionStore


@pytest.mark.parametrize("limit", [1, 2, -1])
def test_route_listing_retains_candidates_after_peer_deletes_stale_row(tmp_path, monkeypatch, limit):
    """Deleting an earlier candidate must not shift the next page."""
    store = SqliteSessionStore(session_dir=str(tmp_path))
    for sid in ("a-stale", "b-healthy", "c-healthy"):
        store.add_message(sid, "user", "retained")
        store.set_gateway_info(sid, agent_id="agent")
    store._ensure_backfilled()
    path = tmp_path / "a-stale.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["agent_id"] = "other"
    path.write_text(json.dumps(data), encoding="utf-8")
    peer = SqliteSessionStore(session_dir=str(tmp_path))
    read = store._read_indexed_route

    def read_with_peer_deletion(sid):
        session = read(sid)
        if sid == "a-stale":
            assert peer.delete_session(sid)
        return session

    monkeypatch.setattr(store, "_read_indexed_route", read_with_peer_deletion)
    expected = ["b-healthy"] if limit == 1 else ["b-healthy", "c-healthy"]
    assert store.list_sessions_by_gateway_agent("agent", limit=limit) == expected


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("after", [None, "a-stale"])
def test_ordered_route_pages_need_no_temporary_sort(tmp_path, existing, after):
    """New and upgraded stores support ordered agent pages with one index."""
    db_path = tmp_path / "index.db"
    if existing:
        legacy = sqlite3.connect(db_path)
        legacy.execute(
            "CREATE TABLE session_route (session_id TEXT PRIMARY KEY, "
            "gateway_session_id TEXT, agent_id TEXT)"
        )
        legacy.execute("CREATE INDEX idx_route_agent ON session_route(agent_id)")
        legacy.close()
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=str(db_path))
    conn = store._connect()
    condition = "" if after is None else "AND session_id > ? "
    params = ("agent", 1) if after is None else ("agent", after, 1)
    try:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT session_id FROM session_route WHERE agent_id = ? "
            + condition + "ORDER BY session_id LIMIT ?", params,
        ).fetchall()
        details = " ".join(row[3] for row in plan).upper()
        assert "TEMP B-TREE" not in details
        assert "COVERING INDEX" in details
    finally:
        conn.close()
