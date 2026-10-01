"""Tests for incremental streamed-turn persistence (Issue #5407).

Streamed assistant output is only persisted after a turn completes, so an
interrupt mid-generation loses the whole in-progress turn. These tests cover
the ``upsert_partial_assistant_message`` / ``discard_partial_assistant_message``
seam on the default JSON store.
"""

import tempfile

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
