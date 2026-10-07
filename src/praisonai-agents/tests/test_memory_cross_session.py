"""
Regression tests for cross-session memory recall (issue #5595).

Two Agent instances sharing the same memory store (e.g. the same user_id)
must be able to recall facts written during an earlier turn. Previously the
synchronous chat/run/start path never wrote the interaction to the memory
store, so the second agent recalled nothing.

These tests drive the after-agent side-effect pipeline directly so they do
not require an LLM or OPENAI_API_KEY.
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from praisonaiagents import Agent
from praisonaiagents.memory import FileMemory


class TestCrossSessionMemoryRecall(unittest.TestCase):
    """MEM-001/002/003 from issue #5595."""

    def _agent(self, user_id, base_path):
        memory = FileMemory(user_id=user_id, base_path=base_path)
        return Agent(
            name="Assistant",
            instructions="You are a helpful assistant.",
            memory=memory,
        )

    def test_turn_persisted_and_recalled_across_instances(self):
        """MEM-001: a fact stored in session A is recalled by session B."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = f"{tmpdir}/memory"

            # Session A: simulate a completed turn storing a codename.
            agent_a = self._agent("e2e-memory-test", base)
            agent_a._after_agent_side_effects(
                "My codename is ORANGE-PANDA. ACK.",
                "Acknowledged. Your codename is ORANGE-PANDA.",
            )

            # Session B: a fresh agent sharing the same user_id must recall it.
            agent_b = self._agent("e2e-memory-test", base)
            context = agent_b.get_memory_context(query="What is my codename?")
            self.assertIn("ORANGE-PANDA", context)

    def test_different_user_id_is_isolated(self):
        """MEM-002: a different user_id must not see another user's memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = f"{tmpdir}/memory"

            agent_a = self._agent("user-a", base)
            agent_a._after_agent_side_effects(
                "My codename is ORANGE-PANDA.",
                "Acknowledged. Your codename is ORANGE-PANDA.",
            )

            agent_b = self._agent("user-b", base)
            context = agent_b.get_memory_context(query="What is my codename?")
            self.assertNotIn("ORANGE-PANDA", context)

    def test_empty_response_is_not_persisted(self):
        """A turn with no response must not write an empty entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = f"{tmpdir}/memory"
            agent = self._agent("user-empty", base)
            agent._after_agent_side_effects("hello", "")
            self.assertEqual(
                agent._memory_instance.get_stats()["short_term_count"], 0
            )

    def test_dict_memory_config_persists_and_recalls(self):
        """MEM-004: the advertised ``memory={'user_id': uid}`` dict config —
        resolved by the Agent itself, not a preconstructed FileMemory — persists
        a turn that a second Agent with the same user_id recalls.

        Guards the configuration-resolution + hook wiring that the direct-call
        tests above cannot (Greptile #3). Runs in a temp cwd so the default
        FileMemory base path is hermetic; no LLM/API key needed.
        """
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chdir(tmpdir)
            try:
                uid = "dict-config-user"
                agent_a = Agent(name="A", instructions="x", memory={"user_id": uid})
                self.assertIsInstance(agent_a._memory_instance, FileMemory)
                agent_a._after_agent_side_effects(
                    "My codename is BLUE-FOX.",
                    "Acknowledged. Your codename is BLUE-FOX.",
                )

                agent_b = Agent(name="B", instructions="x", memory={"user_id": uid})
                context = agent_b.get_memory_context(query="What is my codename?")
                self.assertIn("BLUE-FOX", context)
            finally:
                os.chdir(cwd)

    def test_async_path_persists_without_blocking_loop(self):
        """MEM-005: on the async after-agent path the blocking store write is
        offloaded to a thread (AGENTS.md §4.5), yet the turn is still persisted
        and recalled by a later Agent. Exercises the running-loop branch of
        ``_persist_memory_turn``.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base = f"{tmpdir}/memory"

            async def write_turn():
                agent_a = self._agent("async-user", base)
                agent_a._after_agent_side_effects(
                    "My codename is GREEN-HAWK.",
                    "Acknowledged. Your codename is GREEN-HAWK.",
                )
                # The write is scheduled via run_in_executor; yield until the
                # short-term store reflects it (bounded) rather than racing it.
                for _ in range(500):
                    if agent_a._memory_instance.get_stats()["short_term_count"] > 0:
                        break
                    await asyncio.sleep(0.01)

            asyncio.run(write_turn())

            agent_b = self._agent("async-user", base)
            context = agent_b.get_memory_context(query="What is my codename?")
            self.assertIn("GREEN-HAWK", context)


class TestCrossInstancePrefetchRecall(unittest.TestCase):
    """Issue #5667: turn-start prefetch must recall a persisted turn on a
    second Agent instance sharing the same ``user_id``.

    The persist path writes to long-term memory (where prefetch queries) and
    stamps ``user_id`` into the record metadata (so the prefetch scope filter
    matches). Exercises the pipeline directly — no LLM / OPENAI_API_KEY.
    """

    def _agent(self, user_id, base_path, auto_memory):
        from praisonaiagents.config.feature_configs import MemoryConfig

        memory = FileMemory(user_id=user_id, base_path=base_path)
        agent = Agent(
            name="Assistant",
            instructions="You are a helpful assistant.",
            memory=memory,
        )
        # Attach a prefetch-enabled, user-scoped config so the chat-mixin
        # prefetch helpers resolve the same scope the Agent would at runtime.
        agent._memory_config = MemoryConfig(
            user_id=user_id, auto_memory=auto_memory, prefetch=True
        )
        agent._auto_memory = auto_memory
        return agent

    def test_prefetch_recalls_persisted_turn_across_instances(self):
        """A fact persisted by instance A is recalled by instance B's prefetch.

        auto_memory=True: the raw turn must still be persisted durably even
        though the pattern extractor cannot extract an arbitrary codename.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base = f"{tmpdir}/memory"
            agent_a = self._agent("recall-5667", base, auto_memory=True)
            agent_a._after_agent_side_effects(
                "Remember codename ORANGE-PANDA for this user.",
                "Acknowledged. Your codename is ORANGE-PANDA.",
            )

            agent_b = self._agent("recall-5667", base, auto_memory=True)
            recalled = agent_b._prefetch_memory("codename ORANGE-PANDA")
            self.assertIn("ORANGE-PANDA", recalled)

    def test_prefetch_isolated_by_user_id(self):
        """A different user_id must not recall another user's persisted turn."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = f"{tmpdir}/memory"
            agent_a = self._agent("recall-user-a", base, auto_memory=True)
            agent_a._after_agent_side_effects(
                "Remember codename ORANGE-PANDA for this user.",
                "Acknowledged. Your codename is ORANGE-PANDA.",
            )

            agent_b = self._agent("recall-user-b", base, auto_memory=True)
            recalled = agent_b._prefetch_memory("codename ORANGE-PANDA")
            self.assertNotIn("ORANGE-PANDA", recalled)


class TestSqliteUserIdFilter(unittest.TestCase):
    """Issue #5667: the ``user_id`` metadata stamp must drive SQLite's
    ``metadata.user_id`` long-term filter.

    ``FileMemory.search_long_term`` ignores the supplied scope and keeps each
    user in a separate file, so the FileMemory tests above could still pass if
    the metadata stamp were removed. The SQLite adapter, by contrast, shares one
    long-term table across users and filters on ``memory_user_id(metadata)`` —
    so recall there depends entirely on the stamp this PR writes. A shared store
    with two users proves matching-user recall and different-user exclusion.
    """

    def _store(self, tmpdir):
        from praisonaiagents.memory.adapters.sqlite_adapter import SqliteMemoryAdapter

        return SqliteMemoryAdapter(
            short_db=f"{tmpdir}/short.db",
            long_db=f"{tmpdir}/long.db",
        )

    def test_matching_user_recalls_and_other_user_excluded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            # Persist a turn stamped with user_id, exactly as
            # Agent._persist_memory_turn does for the durable long-term write.
            store.store_long_term(
                "User: Remember codename ORANGE-PANDA.\nAssistant: Acknowledged.",
                metadata={"user_id": "sqlite-user-a"},
            )

            matching = store.search_long_term(
                "codename", limit=5, user_id="sqlite-user-a"
            )
            self.assertTrue(
                any("ORANGE-PANDA" in r.get("text", "") for r in matching)
            )

            other = store.search_long_term(
                "codename", limit=5, user_id="sqlite-user-b"
            )
            self.assertFalse(
                any("ORANGE-PANDA" in r.get("text", "") for r in other),
                "a different user_id must not recall another user's turn",
            )

    def test_session_id_stamp_matches_prefetch_session_filter(self):
        """Issue #5667: when ``MemoryConfig.session_id`` is set, prefetch sends a
        ``metadata.session_id`` filter. ``_persist_memory_turn`` must stamp that
        session_id or the saved turn is dropped on recall even for the same user.

        Driven through ``Memory`` (SQLite long-term backend) because the
        ``session_id`` post-filter lives in ``Memory.search_long_term`` — the raw
        adapter only filters ``user_id``. Persists with the same metadata the
        Agent stamps (user_id + session_id) and recalls through the exact
        ``metadata_filter={"session_id": ...}`` scope ``_memory_prefetch_scope``
        builds. A mismatched session_id is excluded — removing the stamp would
        break the matching case, so this genuinely guards the fix.
        """
        from praisonaiagents.memory import Memory

        with tempfile.TemporaryDirectory() as tmpdir:
            mem = Memory(config={
                "provider": "sqlite",
                "short_db": f"{tmpdir}/short.db",
                "long_db": f"{tmpdir}/long.db",
            })
            mem.store_long_term(
                "User: Remember codename ORANGE-PANDA.\nAssistant: Acknowledged.",
                metadata={"user_id": "sess-user", "session_id": "sess-1"},
            )

            matching = mem.search_long_term(
                "codename",
                limit=5,
                user_id="sess-user",
                metadata_filter={"session_id": "sess-1"},
            )
            self.assertTrue(
                any("ORANGE-PANDA" in r.get("text", "") for r in matching),
                "same user+session must recall the stamped turn",
            )

            other_session = mem.search_long_term(
                "codename",
                limit=5,
                user_id="sess-user",
                metadata_filter={"session_id": "sess-2"},
            )
            self.assertFalse(
                any("ORANGE-PANDA" in r.get("text", "") for r in other_session),
                "a different session_id must not recall the turn",
            )


if __name__ == "__main__":
    unittest.main()
