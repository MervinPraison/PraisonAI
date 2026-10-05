"""Route verification must not skip candidates after a concurrent deletion."""

import json

import pytest

from praisonaiagents.session import SqliteSessionStore


@pytest.mark.parametrize("limit", [1, 2, -1])
def test_route_listing_retains_candidates_after_peer_deletes_stale_row(tmp_path, monkeypatch, limit):
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
