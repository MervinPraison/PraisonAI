"""Tests for incremental streamed-turn persistence (Issue #5407).

Streamed assistant output is only persisted after a turn completes, so an
interrupt mid-generation loses the whole in-progress turn. These tests cover
the ``upsert_partial_assistant_message`` / ``discard_partial_assistant_message``
seam on the default JSON store.
"""

import os
import tempfile

import pytest

from praisonaiagents.session.store import DefaultSessionStore


class TestPartialAssistantPersistence:
    def test_partial_then_resume_retains_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "write a long module")
            store.upsert_partial_assistant_message("s", "chunk one")
            store.upsert_partial_assistant_message("s", "chunk one two")

            # Simulate an interrupt: a fresh store resumes from disk.
            resumed = DefaultSessionStore(session_dir=tmpdir)
            history = resumed.get_chat_history("s")
            assert [m["content"] for m in history] == [
                "write a long module",
                "chunk one two",
            ]

    def test_partial_overwrites_in_place_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            for text in ("a", "ab", "abc"):
                store.upsert_partial_assistant_message("s", text)
            session = store.get_session("s")
            assert len(session.messages) == 2  # user + single assistant
            assert session.messages[-1].content == "abc"
            assert session.messages[-1].metadata.get("partial") is True

    def test_finalize_clears_partial_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "draft")
            store.upsert_partial_assistant_message("s", "final", finalize=True)
            session = store.get_session("s")
            assert len(session.messages) == 2
            assert session.messages[-1].content == "final"
            assert "partial" not in session.messages[-1].metadata

    def test_finalize_without_partial_appends_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "answer", finalize=True)
            session = store.get_session("s")
            assert [m.content for m in session.messages] == ["q", "answer"]
            assert "partial" not in session.messages[-1].metadata

    def test_finalize_empty_drops_blank_partial(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "")
            store.upsert_partial_assistant_message("s", "", finalize=True)
            session = store.get_session("s")
            assert [m.role for m in session.messages] == ["user"]

    def test_discard_removes_partial(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "stale")
            assert store.discard_partial_assistant_message("s") is True
            session = store.get_session("s")
            assert [m.role for m in session.messages] == ["user"]

    def test_discard_leaves_completed_turn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            store.add_assistant_message("s", "done")
            store.discard_partial_assistant_message("s")
            session = store.get_session("s")
            assert [m.content for m in session.messages] == ["q", "done"]

    def test_discard_read_failure_falls_through_to_locked_rmw(self, monkeypatch):
        """An ambiguous precheck read failure must not short-circuit the
        discard as success — it must fall through to the locked RMW so a stale
        partial is still removed (Issue #5407)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "stale")

            calls = {"n": 0}
            real_read = store._read_session_fresh

            def flaky_read(session_id):
                # Fail only the first (precheck) read; the locked RMW re-reads.
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("transient read failure")
                return real_read(session_id)

            monkeypatch.setattr(store, "_read_session_fresh", flaky_read)

            assert store.discard_partial_assistant_message("s") is True
            monkeypatch.undo()
            session = store.get_session("s")
            assert [m.role for m in session.messages] == ["user"]


class TestMemoryMixinSeam:
    """The agent-side helpers degrade gracefully and route to the store."""

    def _agent(self, store, session_id="s"):
        from praisonaiagents.agent.memory_mixin import MemoryMixin

        class _A(MemoryMixin):
            def __init__(self):
                self._session_store = store
                self._session_id = session_id
                self._db = None
                self.auto_save = False

            def _persist_session_stats(self):
                pass

        return _A()

    def test_delta_and_finalize_route_to_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            agent = self._agent(store)
            agent._persist_assistant_delta("partial", force=True)
            assert store.get_session("s").messages[-1].metadata.get("partial") is True
            agent._finalize_assistant_turn("partial done")
            last = store.get_session("s").messages[-1]
            assert last.content == "partial done"
            assert "partial" not in last.metadata

    def test_finalize_falls_back_when_no_partial_support(self):
        class _LegacyStore:
            def __init__(self):
                self.calls = []

            def add_assistant_message(self, session_id, content, metadata=None):
                self.calls.append(("assistant", content))
                return True

            def add_message(self, session_id, role, content, metadata=None):
                self.calls.append((role, content))
                return True

        store = _LegacyStore()
        agent = self._agent(store)
        # No partial support -> delta is a no-op, finalize does one terminal write.
        agent._persist_assistant_delta("x", force=True)
        agent._finalize_assistant_turn("final text")
        assert ("assistant", "final text") in store.calls


class TestFailedFinalizationRecovery:
    """A failed durable write must not silently report success (Issue #5407)."""

    def test_finalize_write_failure_propagates(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "partial")
            # Simulate a disk-full / corruption on the durable write.
            monkeypatch.setattr(
                store, "_atomic_write_json", lambda *a, **k: False
            )
            ok = store.upsert_partial_assistant_message(
                "s", "final answer", finalize=True
            )
            assert ok is False  # failure surfaced, not swallowed


class TestSqliteTranscriptPartialPersistence:
    """The SQLite transcript store must honour partial writes through its
    authoritative row path, not a stray JSON file (Issue #5407)."""

    def _store(self):
        from praisonaiagents.session.sqlite_transcript_store import (
            SqliteTranscriptStore,
        )

        return SqliteTranscriptStore(db_path=":memory:")

    def test_partial_then_finalize_visible_in_row(self):
        store = self._store()
        store.add_user_message("s", "q")
        store.upsert_partial_assistant_message("s", "draft")
        # Read back through the authoritative row, not a JSON file.
        session = store.get_session("s")
        assert session.messages[-1].content == "draft"
        assert session.messages[-1].metadata.get("partial") is True

        store.upsert_partial_assistant_message("s", "final", finalize=True)
        history = store.get_chat_history("s")
        assert [m["content"] for m in history] == ["q", "final"]

    def test_discard_partial_in_row(self):
        store = self._store()
        store.add_user_message("s", "q")
        store.upsert_partial_assistant_message("s", "stale")
        assert store.discard_partial_assistant_message("s") is True
        assert [m["role"] for m in store.get_chat_history("s")] == ["user"]


class TestEncryptedPartialPersistence:
    """Streamed partial content must be encrypted at rest, not forwarded raw
    through ``__getattr__`` (Issue #5407)."""

    def _crypto(self):
        pytest.importorskip("cryptography")

    def test_partial_content_encrypted_on_disk(self):
        self._crypto()
        from praisonaiagents.session.encrypted_store import (
            EncryptedSessionStore,
            generate_session_key,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            key = generate_session_key()
            inner = DefaultSessionStore(session_dir=tmpdir)
            store = EncryptedSessionStore(inner, key=key)
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "secret partial")

            # Raw disk bytes must not contain the plaintext.
            on_disk = ""
            for name in os.listdir(tmpdir):
                if name.endswith(".json"):
                    with open(os.path.join(tmpdir, name)) as fh:
                        on_disk += fh.read()
            assert "secret partial" not in on_disk

            # But the wrapper decrypts it back for the caller.
            history = store.get_chat_history("s")
            assert history[-1]["content"] == "secret partial"

    def test_finalize_encrypted_and_recoverable(self):
        self._crypto()
        from praisonaiagents.session.encrypted_store import (
            EncryptedSessionStore,
            generate_session_key,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            key = generate_session_key()
            store = EncryptedSessionStore(
                DefaultSessionStore(session_dir=tmpdir), key=key
            )
            store.add_user_message("s", "q")
            store.upsert_partial_assistant_message("s", "draft answer")
            store.upsert_partial_assistant_message(
                "s", "final answer", finalize=True
            )
            # Resume with the same key decrypts the finalized turn.
            resumed = EncryptedSessionStore(
                DefaultSessionStore(session_dir=tmpdir), key=key
            )
            history = resumed.get_chat_history("s")
            assert [m["content"] for m in history] == ["q", "final answer"]
