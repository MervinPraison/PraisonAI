"""Tests for the SQLite-backed transcript store (Issue #3407).

Covers:
- Drop-in compatibility with DefaultSessionStore (subclass + protocol).
- Transcripts persist to SQLite rows (not per-session JSON files).
- add_message / get_chat_history / clear / delete / session_exists.
- Indexed listings and gateway/agent routing lookups.
- Cross-process durability (a second store instance sees prior writes).
- Search returns anchored hits identical in shape to the default store.
"""

import os
import tempfile

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session import SqliteTranscriptStore
from praisonaiagents.session.protocols import (
    SessionStoreProtocol,
    SearchableSessionStoreProtocol,
)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestSqliteTranscriptStore:
    def test_is_drop_in_for_default(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir, db_path=":memory:")
        assert isinstance(store, DefaultSessionStore)
        assert isinstance(store, SessionStoreProtocol)
        assert isinstance(store, SearchableSessionStoreProtocol)

    def test_add_and_get_history(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        assert store.add_message("s1", "user", "Hello")
        assert store.add_message("s1", "assistant", "Hi there!")
        history = store.get_chat_history("s1")
        assert history == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

    def test_no_json_files_written(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "no json please")
        files = os.listdir(tmp_dir)
        assert not any(f.endswith(".json") for f in files)
        assert any(f.endswith(".db") for f in files)

    def test_persistence_across_instances(self, tmp_dir):
        db = os.path.join(tmp_dir, "sessions.db")
        s1 = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
        s1.add_message("s1", "user", "persist me")

        s2 = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
        history = s2.get_chat_history("s1")
        assert history == [{"role": "user", "content": "persist me"}]

    def test_session_exists_and_delete(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        assert not store.session_exists("s1")
        store.add_message("s1", "user", "hi")
        assert store.session_exists("s1")
        assert store.delete_session("s1")
        assert not store.session_exists("s1")

    def test_clear_session(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "hi")
        store.add_message("s1", "assistant", "hello")
        assert store.clear_session("s1")
        assert store.get_chat_history("s1") == []
        assert store.session_exists("s1")

    def test_list_sessions(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("a", "user", "one")
        store.add_message("b", "user", "two")
        listed = store.list_sessions()
        ids = {s["session_id"] for s in listed}
        assert ids == {"a", "b"}

    def test_gateway_routing_lookup(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "hi")
        store.set_gateway_info("s1", gateway_session_id="gw-1", agent_id="agent-x")

        found = store.get_by_gateway_session("gw-1")
        assert found is not None
        assert found.session_id == "s1"

        ids = store.list_sessions_by_gateway_agent("agent-x")
        assert ids == ["s1"]

    def test_list_by_agent_name(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "hi")
        store.set_agent_info("s1", agent_name="Support")
        assert store.list_sessions_by_agent("Support") == ["s1"]

    def test_search_finds_session(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "Please help with the billing migration")
        store.add_message("s1", "assistant", "Sure, migrating billing now")
        store.add_message("s2", "user", "unrelated weather chat")

        hits = store.search("billing migration")
        assert len(hits) == 1
        assert hits[0].session_id == "s1"
        assert hits[0].messages  # anchored context returned

    def test_search_empty_query(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "hi")
        assert store.search("") == []

    def test_tool_turns_round_trip(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message(
            "s1",
            "assistant",
            "",
            tool_calls=[{"id": "c1", "type": "function",
                         "function": {"name": "f", "arguments": "{}"}}],
        )
        store.add_message("s1", "tool", "result", tool_call_id="c1")
        session = store.get_session("s1")
        assert session.messages[0].tool_calls[0]["id"] == "c1"
        assert session.messages[1].tool_call_id == "c1"
