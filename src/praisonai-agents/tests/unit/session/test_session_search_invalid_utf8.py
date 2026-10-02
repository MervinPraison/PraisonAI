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
