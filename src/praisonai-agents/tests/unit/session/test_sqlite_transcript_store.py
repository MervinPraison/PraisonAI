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

    def test_boots_on_malformed_db(self, tmp_dir):
        """A malformed transcript DB recovers instead of taking the store down.

        Before Issue #5387's guard, opening a corrupt ``sessions.db`` raised an
        uncaught ``sqlite3.DatabaseError`` on the first ``CREATE TABLE``. The
        guard forensically backs up the bad bytes and lets a fresh, usable store
        open so durable session handling keeps working.
        """
        db = os.path.join(tmp_dir, "sessions.db")
        s1 = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
        s1.add_message("s1", "user", "before corruption")
        s1._conn.close()  # release the file/WAL before corrupting on disk

        # Corrupt the on-disk database so quick_check fails and it is unreadable.
        for sidecar in (db + "-wal", db + "-shm"):
            if os.path.exists(sidecar):
                os.remove(sidecar)
        with open(db, "r+b") as fh:
            fh.write(b"not a sqlite database" + b"\x00" * 300)

        # A new store must open without raising and be usable.
        s2 = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
        assert s2.add_message("s2", "user", "after recovery")
        assert s2.get_chat_history("s2") == [
            {"role": "user", "content": "after recovery"}
        ]
        # The malformed bytes were preserved for forensics.
        assert any(f.startswith("sessions.db.corrupt-") for f in os.listdir(tmp_dir))

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

    def test_concurrent_writers_no_lost_updates(self, tmp_dir):
        """Two independent store instances (simulating two gateway processes)
        appending to the same session concurrently must not drop any message.

        Each ``add_message`` runs a BEGIN IMMEDIATE read-modify-write, so
        SQLite serializes the appends across connections instead of both
        reading the same row and clobbering each other.
        """
        import threading

        db = os.path.join(tmp_dir, "sessions.db")
        writers = 4
        per_writer = 20

        def run(idx):
            store = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
            for j in range(per_writer):
                assert store.add_message("shared", "user", f"{idx}-{j}")

        threads = [threading.Thread(target=run, args=(i,)) for i in range(writers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        reader = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
        history = reader.get_chat_history("shared")
        assert len(history) == writers * per_writer

    def test_migrates_legacy_json_on_first_open(self, tmp_dir):
        """Existing per-session JSON files are imported once when the SQLite
        store first opens beside them (upgrade preserves durable history)."""
        legacy = DefaultSessionStore(session_dir=tmp_dir)
        legacy.add_message("old", "user", "legacy transcript")
        assert any(f.endswith(".json") for f in os.listdir(tmp_dir))

        store = SqliteTranscriptStore(session_dir=tmp_dir)
        assert store.session_exists("old")
        assert store.get_chat_history("old") == [
            {"role": "user", "content": "legacy transcript"}
        ]

    def test_migration_skips_invalid_utf8_legacy_file(self, tmp_dir):
        """A legacy file with invalid UTF-8 bytes is skipped (not fatal), and
        valid transcripts still migrate; the bad bytes are preserved."""
        legacy = DefaultSessionStore(session_dir=tmp_dir)
        legacy.add_message("old", "user", "legacy transcript")

        bad_path = os.path.join(tmp_dir, "invalid.json")
        with open(bad_path, "wb") as handle:
            handle.write(b"\xff\xfe")

        store = SqliteTranscriptStore(session_dir=tmp_dir)
        assert store.session_exists("old")
        assert store.get_chat_history("old") == [
            {"role": "user", "content": "legacy transcript"}
        ]

        with open(bad_path, "rb") as handle:
            assert handle.read() == b"\xff\xfe"

    def test_migration_continues_after_invalid_utf8_ordered_first(self, tmp_dir):
        """A bad file processed before valid ones must not abort later migrations.

        Migration sorts filenames, so ``aaa_invalid.json`` is deterministically
        processed before the ``zeta`` session's JSON file — guaranteeing the
        bad-first scenario is actually exercised.
        """
        legacy = DefaultSessionStore(session_dir=tmp_dir)
        legacy.add_message("zeta", "user", "valid transcript")

        bad_path = os.path.join(tmp_dir, "aaa_invalid.json")
        with open(bad_path, "wb") as handle:
            handle.write(b"\xff\xfe")

        import json as _json

        json_files = sorted(f for f in os.listdir(tmp_dir) if f.endswith(".json"))
        assert json_files[0] == "aaa_invalid.json"
        valid_file = next(
            f for f in json_files
            if f != "aaa_invalid.json" and "zeta" in _json.dumps(
                _json.load(open(os.path.join(tmp_dir, f)))
            )
        )
        assert "aaa_invalid.json" < valid_file

        store = SqliteTranscriptStore(session_dir=tmp_dir)
        assert store.session_exists("zeta")
        assert store.get_chat_history("zeta") == [
            {"role": "user", "content": "valid transcript"}
        ]


class TestTranscriptPortability:
    """Issue #5517: export/import must read/write DB rows, not JSON sidecars."""

    def test_export_all_includes_db_sessions(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "hello db")
        store.add_message("s2", "user", "second db")
        payload = store.export_all()
        assert payload["version"] == store.PORTABLE_VERSION
        ids = {s["session_id"] for s in payload["sessions"]}
        assert ids == {"s1", "s2"}

    def test_export_all_ignores_unrelated_json_sidecars(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "db only")
        # Drop an unrelated JSON sidecar next to the DB; it must not leak in.
        with open(os.path.join(tmp_dir, "stray.json"), "w", encoding="utf-8") as f:
            f.write('{"session_id": "stray", "messages": []}')
        payload = store.export_all()
        ids = {s["session_id"] for s in payload["sessions"]}
        assert ids == {"s1"}

    def test_export_session_includes_db_lineage(self, tmp_dir):
        from praisonaiagents.session.store import SessionData

        store = SqliteTranscriptStore(session_dir=tmp_dir)
        for sid in ("root", "cont"):
            session = SessionData(session_id=sid, metadata={"lineage_id": "L1"})
            store._save_session(session)
        payload = store.export_session("root")
        ids = {s["session_id"] for s in payload["sessions"]}
        assert ids == {"root", "cont"}

    def test_import_writes_db_row_over_existing(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        store.add_message("s1", "user", "original")

        payload = {
            "version": store.PORTABLE_VERSION,
            "sessions": [
                {
                    "session_id": "s1",
                    "messages": [
                        {"role": "user", "content": "restored"},
                    ],
                }
            ],
        }
        report = store.import_sessions(payload, overwrite=True)
        assert report.imported == 1
        # The restore must be visible in the DB, not written to a JSON sidecar.
        assert store.session_exists("s1")
        assert not any(f.endswith(".json") for f in os.listdir(tmp_dir))
        reader = SqliteTranscriptStore(
            session_dir=tmp_dir, db_path=store.db_path
        )
        assert reader.get_chat_history("s1") == [
            {"role": "user", "content": "restored"}
        ]

    def test_import_read_only_db_reports_failure(self, tmp_dir):
        db = os.path.join(tmp_dir, "sessions.db")
        store = SqliteTranscriptStore(session_dir=tmp_dir, db_path=db)
        store.add_message("s1", "user", "existing")
        # Make the live connection read-only; an overwrite must fail, not lie.
        store._connect().execute("PRAGMA query_only=ON")

        payload = {
            "version": store.PORTABLE_VERSION,
            "sessions": [
                {"session_id": "s1", "messages": [{"role": "user", "content": "x"}]}
            ],
        }
        report = store.import_sessions(payload, overwrite=True)
        assert report.imported == 0
        assert report.skipped  # write failure reported, not silent success

    def test_round_trip_to_fresh_store(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir, db_path=":memory:")
        store.add_message("s1", "user", "one")
        store.add_message("s2", "user", "two")
        payload = store.export_all()

        dest = SqliteTranscriptStore(session_dir=tmp_dir + "2", db_path=":memory:")
        report = dest.import_sessions(payload)
        assert report.imported == 2
        assert dest.session_exists("s1")
        assert dest.session_exists("s2")

    def test_import_preserves_history_over_destination_window(self, tmp_dir):
        # Guards the no-window-truncation restore contract on the SQLite
        # backend: a destination with a small truncating window must not drop
        # exported history on import (regression guard if the restore path ever
        # switched from _save_imported_session to _save_session).
        src = SqliteTranscriptStore(session_dir=tmp_dir)
        for i in range(6):
            src.add_message("s1", "user", f"m{i}")
        payload = src.export_all()

        db = os.path.join(tmp_dir, "dest.db")
        dst = SqliteTranscriptStore(
            session_dir=tmp_dir + "2",
            db_path=db,
            active_window=2,
            retention="truncate",
        )
        assert dst.import_sessions(payload).imported == 1

        reader = SqliteTranscriptStore(session_dir=tmp_dir + "2", db_path=db)
        session = reader.get_session("s1")
        restored = session.archived_messages + session.messages
        assert [m.content for m in restored] == [f"m{i}" for i in range(6)]


class TestTranscriptArchivedRecall:
    """Issue #5031: transcript store must recall compacted (archived) turns."""

    def _seed_with_archive(self, store, session_id, archived, active):
        from praisonaiagents.session.store import SessionData, SessionMessage

        session = SessionData(session_id=session_id)
        for role, content in archived:
            session.archived_messages.append(
                SessionMessage(role=role, content=content)
            )
        for role, content in active:
            session.messages.append(SessionMessage(role=role, content=content))
        store._save_session(session)

    def test_recalls_archived_only_token(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        self._seed_with_archive(
            store,
            "s1",
            archived=[("user", "the special value was zx-9271-alpha")],
            active=[("system", "Summary: helped set up X")],
        )
        hits = store.search("zx-9271-alpha")
        assert [h.session_id for h in hits] == ["s1"]
        assert any(m.get("archived") for m in hits[0].messages)

    def test_real_compaction_stays_searchable(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir, active_window=3)
        store.add_message("s", "user", "the special value was zx-9271-alpha")
        for i in range(8):
            store.add_message("s", "user", f"later message {i}")

        session = store.get_session("s")
        archived = [m.content for m in session.archived_messages]
        assert "the special value was zx-9271-alpha" in archived

        hits = store.search("zx-9271-alpha")
        assert [h.session_id for h in hits] == ["s"]

    def test_window_scrolls_from_archived_anchor(self, tmp_dir):
        store = SqliteTranscriptStore(session_dir=tmp_dir)
        self._seed_with_archive(
            store,
            "s1",
            archived=[
                ("user", "the special value was zx-9271-alpha"),
                ("assistant", "noted the special value"),
            ],
            active=[
                ("system", "Summary: helped set up X"),
                ("user", "unrelated recent turn"),
            ],
        )
        hits = store.search("zx-9271-alpha")
        assert hits and hits[0].session_id == "s1"
        rows = store.window("s1", str(hits[0].anchor_index), window=1)
        contents = " ".join(r["content"] for r in rows)
        assert "zx-9271-alpha" in contents
        assert any(r.get("archived") for r in rows)
