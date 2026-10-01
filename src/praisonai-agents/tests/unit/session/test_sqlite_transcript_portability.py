"""Portable session operations use the SQLite transcript persistence backend."""

import json

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore


@pytest.fixture
def stores(tmp_path):
    opened = []

    def make(name, backend=SqliteTranscriptStore, **kwargs):
        store = backend(session_dir=str(tmp_path / name), **kwargs)
        opened.append(store)
        return store

    yield make
    for store in opened:
        conn = getattr(store, "_conn", None)
        if conn is not None:
            conn.close()


def test_export_all_reads_database_not_json_sidecars(stores):
    store = stores("source")
    assert store.add_message("one", "user", "First")
    assert store.add_message("two", "assistant", "Second")
    from pathlib import Path
    (Path(store.session_dir) / "unrelated.json").write_text(
        json.dumps({"session_id": "sidecar", "messages": []}), encoding="utf-8"
    )
    payload = store.export_all()
    assert payload["version"] == store.PORTABLE_VERSION
    assert {record["session_id"] for record in payload["sessions"]} == {"one", "two"}


@pytest.mark.parametrize("key", ["lineage_id", "root_session_id", "thread_id"])
def test_single_export_includes_database_lineage(stores, key):
    store = stores("source")
    for session_id in ("first", "continuation", "unrelated"):
        assert store.add_message(session_id, "user", session_id)
        assert store.update_session_metadata(session_id, **{key: "shared" if session_id != "unrelated" else "other"})
    payload = store.export_session("continuation")
    assert {record["session_id"] for record in payload["sessions"]} == {"first", "continuation"}
    assert [record["session_id"] for record in store.export_session("continuation", include_lineage=False)["sessions"]] == ["continuation"]


@pytest.mark.parametrize("source_backend", [DefaultSessionStore, SqliteTranscriptStore])
@pytest.mark.parametrize("target_backend", [DefaultSessionStore, SqliteTranscriptStore])
def test_cross_backend_restore_survives_reopen_without_window_truncation(stores, source_backend, target_backend):
    source = stores("source", source_backend)
    for index in range(6):
        assert source.add_message("reference", "user", f"message-{index}")
    assert source.set_gateway_info("reference", gateway_session_id="live", agent_id="agent")
    payload = source.export_all()
    assert len(payload["sessions"]) == 1
    target = stores("target", target_backend, active_window=2, retention="truncate")
    # An existing SQLite row prevents legacy JSON migration from masking a
    # restore incorrectly written to a sidecar file instead of the database.
    assert target.add_message("existing", "user", "Existing history")
    assert target.import_sessions(payload).imported == 1
    assert target.session_exists("reference")
    target.invalidate_cache()
    reopened = stores("target", target_backend, active_window=2, retention="truncate")
    for current in (target, reopened):
        assert [message["content"] for message in current.get_chat_history("reference")] == [f"message-{index}" for index in range(6)]
        session = current.get_session("reference")
        assert session.gateway_session_id is None
        assert session.agent_id is None
    if target_backend is SqliteTranscriptStore:
        from pathlib import Path
        assert list(Path(target.session_dir).glob("*.json")) == []


def test_import_sqlite_write_failure_is_reported_and_preserves_existing_row(stores):
    source = stores("source", DefaultSessionStore)
    assert source.add_message("reference", "user", "New history")
    target = stores("target")
    assert target.add_message("reference", "user", "Original history")
    target._connect().execute("PRAGMA query_only=ON")
    report = target.import_sessions(source.export_all(), overwrite=True)
    assert report.imported == 0
    assert report.skipped_count == 1
    assert "write failed" in report.skipped[0]["reason"]
    target.invalidate_cache()
    assert target.get_chat_history("reference")[0]["content"] == "Original history"


@pytest.mark.parametrize("reset_live_fields", [True, False])
def test_restore_preserves_archived_history_and_tool_calls(stores, reset_live_fields):
    tool_calls = [{"id": "call-1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]
    payload = {"sessions": [{
        "session_id": "reference",
        "gateway_session_id": "live",
        "agent_id": "agent",
        "metadata": {"gateway_session_id": "live", "agent_id": "agent", "lineage_id": "shared"},
        "archived_messages": [{"role": "user", "content": "Archived", "timestamp": 1}],
        "messages": [{"role": "assistant", "content": "Tool call", "tool_calls": tool_calls}],
    }]}
    target = stores("target", active_window=1, retention="truncate")
    assert target.add_message("existing", "user", "Existing")
    assert target.import_sessions(payload, reset_live_fields=reset_live_fields).imported == 1
    record = stores("target").export_session("reference")["sessions"][0]
    assert record["messages"][0]["tool_calls"] == tool_calls
    assert record["archived_messages"][0]["content"] == "Archived"
    assert record["metadata"]["lineage_id"] == "shared"
    if reset_live_fields:
        assert record.get("gateway_session_id") is None
        assert record.get("agent_id") is None
        assert "gateway_session_id" not in record["metadata"]
        assert "agent_id" not in record["metadata"]
    else:
        assert record["gateway_session_id"] == "live"
        assert record["agent_id"] == "agent"
        assert record["metadata"]["gateway_session_id"] == "live"
        assert record["metadata"]["agent_id"] == "agent"


def test_sqlite_restore_keeps_import_guards(stores):
    source = stores("source", DefaultSessionStore)
    assert source.add_message("reference", "user", "Original")
    payload = source.export_all()
    payload["sessions"].append(dict(payload["sessions"][0]))
    target = stores("target")
    report = target.import_sessions(payload)
    assert report.imported == 1
    assert "duplicate" in report.skipped[0]["reason"]
    assert target.import_sessions(payload).imported == 0
    assert target.import_sessions(payload, overwrite=True).imported == 1
    assert target.export_session("missing")["sessions"] == []
    payload["version"] = target.PORTABLE_VERSION + 1
    assert target.import_sessions(payload, overwrite=True).imported == 0
    assert target.get_chat_history("reference")[0]["content"] == "Original"
