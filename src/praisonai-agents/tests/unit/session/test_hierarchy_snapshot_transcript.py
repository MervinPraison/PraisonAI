"""Snapshots must restore their transcript after the live window moves."""

import json

import pytest

from praisonaiagents.session.hierarchy import HierarchicalSessionStore, SessionSnapshot
from praisonaiagents.session.store import CompactionCheckpoint, SessionData, SessionMessage


@pytest.mark.parametrize("retention", ["compact", "truncate", "keep_all"])
def test_snapshot_survives_retention_and_reopen(tmp_path, retention):
    store = HierarchicalSessionStore(
        session_dir=str(tmp_path), max_messages=100, active_window=2,
        retention=retention,
    )
    for content in ["one", "two"]:
        assert store.add_message("parent", "user", content)
    before = json.loads((tmp_path / "parent.json").read_text(encoding="utf-8"))
    snapshot_id = store.create_snapshot("parent")
    for content in ["three", "four"]:
        assert store.add_message("parent", "user", content)
    reopened = HierarchicalSessionStore(
        session_dir=str(tmp_path), max_messages=100, active_window=2,
        retention=retention,
    )

    assert reopened.revert_to_snapshot("parent", snapshot_id)

    restored = json.loads((tmp_path / "parent.json").read_text(encoding="utf-8"))
    assert restored["messages"] == before["messages"]
    assert restored["archived_messages"] == before["archived_messages"]
    assert restored.get("last_compaction") == before.get("last_compaction")


@pytest.mark.parametrize("retention", ["compact", "truncate", "keep_all"])
def test_snapshot_restores_large_import_without_reapplying_window(tmp_path, retention):
    store = HierarchicalSessionStore(
        session_dir=str(tmp_path), max_messages=100, active_window=2, retention=retention
    )
    exported = SessionData(
        session_id="source",
        messages=[SessionMessage("user", str(index), timestamp=index) for index in range(5)],
        archived_messages=[SessionMessage("user", "archived", timestamp=-1)],
    ).to_dict()
    session_id = store.import_session(exported)
    snapshot_id = store.create_snapshot(session_id)
    live = json.loads((tmp_path / f"{session_id}.json").read_text(encoding="utf-8"))
    assert live["messages"] == exported["messages"]
    assert live["archived_messages"] == exported["archived_messages"]
    assert store.add_message(session_id, "user", "later")

    assert store.revert_to_snapshot(session_id, snapshot_id)

    saved = json.loads((tmp_path / f"{session_id}.json").read_text(encoding="utf-8"))
    assert saved["messages"] == exported["messages"]
    assert saved["archived_messages"] == exported["archived_messages"]


def test_empty_snapshot_removes_later_archive_and_messages(tmp_path):
    store = HierarchicalSessionStore(
        session_dir=str(tmp_path), max_messages=100, active_window=2, retention="compact"
    )
    store.create_session(session_id="parent")
    snapshot_id = store.create_snapshot("parent")
    for content in ["one", "two", "three", "four"]:
        assert store.add_message("parent", "user", content)
    assert store.export_session("parent")["archived_messages"]

    assert store.revert_to_snapshot("parent", snapshot_id)

    restored = store.export_session("parent")
    assert restored["messages"] == []
    assert restored["archived_messages"] == []


def test_legacy_snapshot_without_window_change_remains_compatible(tmp_path):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("parent", "user", "one")
    path = tmp_path / "parent.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    legacy = SessionSnapshot(id="legacy", session_id="parent", message_index=0).to_dict()
    assert "transcript" not in legacy
    data["snapshots"] = [legacy]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert store.add_message("parent", "user", "two")

    assert store.revert_to_snapshot("parent", "legacy")
    assert [message["content"] for message in store.export_session("parent")["messages"]] == ["one"]


@pytest.mark.parametrize("retention", ["compact", "truncate"])
def test_legacy_snapshot_is_rejected_after_window_change(tmp_path, retention):
    store = HierarchicalSessionStore(
        session_dir=str(tmp_path), max_messages=100, active_window=2, retention=retention
    )
    for content in ["one", "two"]:
        assert store.add_message("parent", "user", content)
    path = tmp_path / "parent.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["snapshots"] = [SessionSnapshot(id="legacy", session_id="parent", message_index=1).to_dict()]
    path.write_text(json.dumps(data), encoding="utf-8")
    for content in ["three", "four"]:
        assert store.add_message("parent", "user", content)
    before = path.read_bytes()

    assert store.revert_to_snapshot("parent", "legacy") is False
    assert path.read_bytes() == before


def test_persisted_snapshot_restores_structured_turns_archive_and_checkpoint(tmp_path):
    calls = [{"id": "call1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]
    captured = SessionData(
        session_id="parent",
        messages=[SessionMessage("assistant", "", timestamp=1, tool_calls=calls),
                  SessionMessage("tool", "result", timestamp=2, tool_call_id="call1")],
        archived_messages=[SessionMessage("user", "early", timestamp=0)],
        last_compaction=CompactionCheckpoint(summary="saved summary", message_index=1),
    ).to_dict()
    transcript = {key: captured[key] for key in ["messages", "archived_messages", "last_compaction"]}
    snapshot = SessionSnapshot(id="saved", session_id="parent", transcript=transcript)
    live = SessionData(session_id="parent", messages=[SessionMessage("user", "later")]).to_dict()
    live["snapshots"] = [snapshot.to_dict()]
    path = tmp_path / "parent.json"
    path.write_text(json.dumps(live), encoding="utf-8")
    store = HierarchicalSessionStore(session_dir=str(tmp_path), active_window=1, retention="truncate")

    assert store.revert_to_snapshot("parent", "saved")

    restored = json.loads(path.read_text(encoding="utf-8"))
    for key, value in transcript.items():
        assert restored[key] == value


def test_failed_restore_preserves_durable_file_and_snapshot(tmp_path, monkeypatch):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("parent", "user", "one")
    snapshot_id = store.create_snapshot("parent")
    assert store.add_message("parent", "user", "two")
    path = tmp_path / "parent.json"
    before = path.read_bytes()
    original = store._atomic_write_json
    monkeypatch.setattr(store, "_atomic_write_json", lambda *args: False)

    assert store.revert_to_snapshot("parent", snapshot_id) is False
    assert path.read_bytes() == before
    monkeypatch.setattr(store, "_atomic_write_json", original)
    assert store.revert_to_snapshot("parent", snapshot_id)
    assert [message["content"] for message in store.export_session("parent")["messages"]] == ["one"]


def test_legacy_snapshot_stays_invalid_after_manual_revert_and_append(tmp_path):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    for content in ["one", "two"]:
        assert store.add_message("parent", "user", content)
    path = tmp_path / "parent.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["snapshots"] = [SessionSnapshot(id="legacy", session_id="parent", message_index=1).to_dict()]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert store.revert_to_message("parent", 0)
    assert store.add_message("parent", "user", "replacement")
    before = path.read_bytes()

    assert store.revert_to_snapshot("parent", "legacy") is False
    assert path.read_bytes() == before


def test_new_snapshot_captures_existing_durable_compaction_checkpoint(tmp_path):
    store = HierarchicalSessionStore(session_dir=str(tmp_path), retention="keep_all")
    assert store.add_message("parent", "user", "one")
    path = tmp_path / "parent.json"
    assert store.append_compaction_checkpoint("parent", "checkpoint")
    checkpoint = json.loads(path.read_text(encoding="utf-8"))["last_compaction"]

    snapshot_id = store.create_snapshot("parent")
    assert store.add_message("parent", "user", "later")
    assert store.revert_to_snapshot("parent", snapshot_id)

    assert json.loads(path.read_text(encoding="utf-8"))["last_compaction"] == checkpoint
