"""N4 — Inbound Dead-Letter Queue for BotSessionManager.

Tests written first (TDD). Implementation in praisonai/bots/_dlq.py.
"""
from __future__ import annotations

import pytest


# ─── Smoke / basic API ───────────────────────────────────────────────
class TestDLQBasic:
    def test_import_and_construct(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        assert dlq.path == tmp_path / "dlq.sqlite"
        assert dlq.size() == 0

    def test_enqueue_then_size_one(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        dlq.enqueue(
            platform="telegram",
            user_id="12345",
            prompt="hello",
            error="LLMTimeout",
        )
        assert dlq.size() == 1

    def test_list_returns_entries(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        dlq.enqueue(platform="discord", user_id="u1", prompt="hi", error="X")
        dlq.enqueue(platform="discord", user_id="u2", prompt="hey", error="Y")
        entries = dlq.list()
        assert len(entries) == 2
        # newest first
        assert entries[0].user_id in {"u1", "u2"}

    def test_purge_clears_queue(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        dlq.enqueue(platform="t", user_id="u", prompt="p", error="e")
        assert dlq.size() == 1
        dlq.purge()
        assert dlq.size() == 0


# ─── Persistence ─────────────────────────────────────────────────────
class TestDLQPersistence:
    def test_survives_restart(self, tmp_path):
        from praisonai.bots import InboundDLQ
        path = tmp_path / "dlq.sqlite"
        dlq1 = InboundDLQ(path=path)
        dlq1.enqueue(platform="t", user_id="u", prompt="hi", error="e")

        dlq2 = InboundDLQ(path=path)
        assert dlq2.size() == 1


# ─── Bounds & TTL ────────────────────────────────────────────────────
class TestDLQBounds:
    def test_max_size_drops_oldest(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite", max_size=3)
        for i in range(5):
            dlq.enqueue(
                platform="t", user_id=f"u{i}",
                prompt=f"msg{i}", error="boom",
            )
        assert dlq.size() == 3
        # Newest 3 retained
        users = {e.user_id for e in dlq.list()}
        assert users == {"u2", "u3", "u4"}

    def test_ttl_evicts_old(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(
            path=tmp_path / "dlq.sqlite",
            ttl_seconds=0,  # everything is "expired" immediately
        )
        dlq.enqueue(platform="t", user_id="u", prompt="p", error="e")
        # Enqueue itself runs eviction
        dlq.evict_expired()
        assert dlq.size() == 0


# ─── Replay ──────────────────────────────────────────────────────────
class TestDLQReplay:
    @pytest.mark.asyncio
    async def test_replay_invokes_callback_per_entry(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        dlq.enqueue(platform="t", user_id="u1", prompt="m1", error="e")
        dlq.enqueue(platform="t", user_id="u2", prompt="m2", error="e")

        seen = []

        async def replayer(entry):
            seen.append((entry.user_id, entry.prompt))
            return True  # success → drop entry

        succeeded, failed = await dlq.replay(replayer)
        assert succeeded == 2
        assert failed == 0
        assert dlq.size() == 0
        assert {x[0] for x in seen} == {"u1", "u2"}

    @pytest.mark.asyncio
    async def test_replay_keeps_failed_entries(self, tmp_path):
        from praisonai.bots import InboundDLQ
        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        dlq.enqueue(platform="t", user_id="u", prompt="m", error="e")

        async def failing_replayer(entry):
            return False

        succeeded, failed = await dlq.replay(failing_replayer)
        assert succeeded == 0
        assert failed == 1
        assert dlq.size() == 1  # entry retained


# ─── Wired into BotSessionManager.chat() ─────────────────────────────
class TestSessionManagerEnqueuesOnFailure:
    @pytest.mark.asyncio
    async def test_chat_enqueues_when_agent_raises(self, tmp_path):
        from praisonai.bots import BotSessionManager, InboundDLQ

        class FailingAgent:
            chat_history = []
            def chat(self, prompt):
                raise RuntimeError("LLM 503")

        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        mgr = BotSessionManager(platform="telegram", dlq=dlq)

        with pytest.raises(RuntimeError):
            await mgr.chat(FailingAgent(), "12345", "hello")

        assert dlq.size() == 1
        e = dlq.list()[0]
        assert e.platform == "telegram"
        assert e.user_id == "12345"
        assert e.prompt == "hello"
        assert "LLM 503" in e.error

    @pytest.mark.asyncio
    async def test_chat_no_dlq_when_no_dlq_configured(self, tmp_path):
        """Default behaviour preserved: no DLQ, error bubbles up."""
        from praisonai.bots import BotSessionManager

        class FailingAgent:
            chat_history = []
            def chat(self, prompt):
                raise RuntimeError("LLM 503")

        mgr = BotSessionManager(platform="telegram")  # no dlq=
        with pytest.raises(RuntimeError):
            await mgr.chat(FailingAgent(), "12345", "hello")
        # No exception about DLQ; nothing persisted (default behaviour)
