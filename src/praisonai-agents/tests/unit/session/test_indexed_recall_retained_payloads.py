"""Indexed recall releases candidate payloads while preserving lineage ranking."""

import json
import weakref

import pytest

from praisonaiagents.session.sqlite_store import SqliteSessionStore


@pytest.mark.parametrize("backend", ["fts", "like"])
def test_search_does_not_retain_every_continuation(tmp_path, monkeypatch, backend):
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    try:
        for index in range(30):
            sid = f"continuation{index:02}"
            assert store.add_message(sid, "user", "needle " + "filler " * 100)
            assert store.update_session_metadata(sid, lineage_id="conversation")
        assert store.add_message("other", "user", "needle " + "filler " * 100)
        assert store.add_message("continuation29", "assistant", "needle best continuation")
        store._ensure_backfilled()
        if backend == "like":
            store._fts_available = False

        class Payload(dict):
            pass

        original = json.load
        references = []
        peak = 0

        def tracked_load(handle, *args, **kwargs):
            nonlocal peak
            value = original(handle, *args, **kwargs)
            if isinstance(value, dict) and str(handle.name).endswith(".json"):
                value = Payload(value)
                references.append(weakref.ref(value))
                peak = max(peak, sum(ref() is not None for ref in references))
            return value

        monkeypatch.setattr(json, "load", tracked_load)
        hits = store.search("needle", limit=5)
        assert len(references) == 31
        assert {hit.session_id for hit in hits} == {"continuation29", "other"}
        assert hits[0].session_id == "continuation29"
        assert peak <= 2
    finally:
        store._conn.close()


def test_lineage_winner_keeps_original_tie_order(tmp_path):
    store = SqliteSessionStore(session_dir=str(tmp_path), db_path=":memory:")
    try:
        for sid, lineage, count in [("00", "a", 1), ("01", "b", 2), ("02", "a", 2)]:
            for _ in range(count):
                assert store.add_message(sid, "user", "needle")
            assert store.update_session_metadata(sid, lineage_id=lineage)
            path = tmp_path / f"{sid}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["updated_at"] = "2026-01-01T00:00:00+00:00"
            path.write_text(json.dumps(data), encoding="utf-8")
        store._ensure_backfilled()
        store._fts_available = False
        assert [hit.session_id for hit in store.search("needle")] == ["01", "02"]
    finally:
        store._conn.close()
