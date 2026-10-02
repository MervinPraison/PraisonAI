"""Durable snapshot pooling must preserve portable and independent transcripts."""

import copy
import json

import pytest

from praisonaiagents.session.hierarchy import (
    ExtendedSessionData, HierarchicalSessionStore, SessionSnapshot,
)
from praisonaiagents.session.store import SessionData, SessionMessage


def test_repeated_snapshots_share_archive_on_disk_and_export_in_full(tmp_path):
    source = SessionData(
        session_id="source",
        messages=[SessionMessage("user", "live", timestamp=1)],
        archived_messages=[SessionMessage("user", "archive-marker-" + str(i) + "x" * 2048,
                                          timestamp=i) for i in range(100)],
    ).to_dict()
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    sid = store.import_session(source, new_session_id="s")
    path = tmp_path / "s.json"
    initial = path.stat().st_size
    ids = [store.create_snapshot(sid) for _ in range(10)]
    assert store.add_message(sid, "user", "later")

    assert path.read_text(encoding="utf-8").count("archive-marker-0x") == 2
    assert path.stat().st_size < initial * 3
    reopened = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    exported = reopened.export_session(sid)
    assert "snapshot_storage" not in exported
    assert all(s["transcript"]["archived_messages"] == source["archived_messages"]
               for s in exported["snapshots"])
    assert all("transcript_refs" not in s for s in exported["snapshots"])
    imported = reopened.import_session(json.loads(json.dumps(exported)), new_session_id="copy")
    assert reopened.revert_to_snapshot(imported, ids[0])
    assert reopened.export_session(imported)["messages"] == source["messages"]


def test_ordinary_write_does_not_expand_portable_snapshot_dicts(tmp_path, monkeypatch):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("s", "user", "first")
    snapshot_id = store.create_snapshot("s")

    def no_portable_copy(self):
        raise AssertionError("ordinary write expanded a portable snapshot")

    monkeypatch.setattr(SessionSnapshot, "to_dict", no_portable_copy)
    assert store.add_message("s", "user", "second")
    assert store.revert_to_snapshot("s", snapshot_id)


def test_positional_reader_rejects_pooled_snapshot_without_losing_real_flag(tmp_path):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("s", "user", "first")
    snapshot_id = store.create_snapshot("s")
    record = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    legacy_view = SessionSnapshot.from_dict(record["snapshots"][0])
    assert legacy_view.transcript is None
    assert legacy_view.invalidated is True
    assert store.revert_to_snapshot("s", snapshot_id)
    record["snapshots"][0]["transcript_invalidated"] = True
    assert ExtendedSessionData.from_dict(record).snapshots[0].invalidated is True


def test_legacy_transcripts_upgrade_and_pooled_values_remain_independent(tmp_path):
    transcript = {"messages": [{"role": "user", "content": [{"text": "old"}], "timestamp": 1}],
                  "archived_messages": [], "last_compaction": None}
    record = ExtendedSessionData(session_id="s", snapshots=[
        SessionSnapshot(id="a", transcript=copy.deepcopy(transcript)),
        SessionSnapshot(id="b", transcript=copy.deepcopy(transcript)),
        SessionSnapshot(id="empty", transcript={}),
    ]).to_dict()
    (tmp_path / "s.json").write_text(json.dumps(record), encoding="utf-8")
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("s", "user", "new")
    reopened = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    snapshots = reopened.get_snapshots("s")
    snapshots[0].transcript["messages"][0]["content"][0]["text"] = "changed"
    assert snapshots[1].transcript == transcript
    assert snapshots[2].transcript == {}
    assert reopened.export_session("s")["snapshots"][0]["transcript"] == transcript


@pytest.mark.parametrize("damage", ["missing", "version", "descriptor"])
def test_invalid_pool_preserves_durable_record_on_write(tmp_path, damage):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("s", "user", "first")
    store.create_snapshot("s")
    path = tmp_path / "s.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    if damage == "missing":
        record["snapshot_storage"]["records"] = {}
    elif damage == "version":
        record["snapshot_storage"]["version"] = 2
    else:
        record["snapshots"][0]["transcript_refs"]["messages"] = {"bad": "ref"}
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    assert store.add_message("s", "user", "must not replace the record") is False
    assert path.read_bytes() == before


@pytest.mark.parametrize("missing", ["messages", "archived_messages", "last_compaction"])
def test_incomplete_pool_cannot_replace_live_history(tmp_path, missing):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("s", "user", "first")
    snapshot_id = store.create_snapshot("s")
    assert store.add_message("s", "user", "later")
    path = tmp_path / "s.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    del record["snapshots"][0]["transcript_refs"][missing]
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="incomplete snapshot"):
        ExtendedSessionData.from_dict(record)
    assert store.revert_to_snapshot("s", snapshot_id) is False
    assert path.read_bytes() == before
    assert store.add_message("s", "user", "must not overwrite") is False
    assert path.read_bytes() == before


@pytest.mark.parametrize("damage", ["message_descriptor", "archive_descriptor", "message_record", "checkpoint_record"])
def test_wrong_reference_types_cannot_replace_live_history(tmp_path, damage):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("s", "user", "first")
    snapshot_id = store.create_snapshot("s")
    assert store.add_message("s", "user", "later")
    path = tmp_path / "s.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    records = record["snapshot_storage"]["records"]
    refs = record["snapshots"][0]["transcript_refs"]
    if damage.endswith("descriptor"):
        records["damaged"] = []
        field = "messages" if damage == "message_descriptor" else "archived_messages"
        refs[field] = {"value": "damaged"}
    elif damage == "message_record":
        records[refs["messages"]["items"][0]] = "not a message"
    else:
        records[refs["last_compaction"]["value"]] = []
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError, match="snapshot"):
        ExtendedSessionData.from_dict(record)
    assert store.revert_to_snapshot("s", snapshot_id) is False
    assert store.add_message("s", "user", "must not overwrite") is False
    assert path.read_bytes() == before
