"""
Regression tests for cross-session memory recall (issue #5595).

Two Agent instances sharing the same memory store (e.g. the same user_id)
must be able to recall facts written during an earlier turn. Previously the
synchronous chat/run/start path never wrote the interaction to the memory
store, so the second agent recalled nothing.

These tests drive the after-agent side-effect pipeline directly so they do
not require an LLM or OPENAI_API_KEY.
"""

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


if __name__ == "__main__":
    unittest.main()
