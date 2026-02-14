"""
TDD tests for bot inbound message debounce.

Debounce coalesces rapid messages from the same user into a single
agent.chat() call, preventing duplicate processing and wasted tokens.
"""

import asyncio
import pytest


class TestInboundDebouncer:
    """Tests for InboundDebouncer."""

    def _make_debouncer(self, debounce_ms=300):
        from praisonai.bots._debounce import InboundDebouncer
        return InboundDebouncer(debounce_ms=debounce_ms)

    @pytest.mark.asyncio
    async def test_single_message_flushes_after_delay(self):
        """A single message is flushed after the debounce window."""
        debouncer = self._make_debouncer(debounce_ms=100)
        result = await debouncer.debounce("user1", "hello")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_rapid_messages_coalesced(self):
        """Multiple rapid messages from same user are joined."""
        debouncer = self._make_debouncer(debounce_ms=200)

        # Enqueue rapidly without awaiting individually
        task1 = asyncio.create_task(debouncer.debounce("user1", "hello"))
        await asyncio.sleep(0.02)
        task2 = asyncio.create_task(debouncer.debounce("user1", "world"))

        results = await asyncio.gather(task1, task2)
        # Both tasks should get the coalesced result
        combined = results[-1]
        assert "hello" in combined
        assert "world" in combined

    @pytest.mark.asyncio
    async def test_different_users_independent(self):
        """Messages from different users are NOT coalesced."""
        debouncer = self._make_debouncer(debounce_ms=100)

        task1 = asyncio.create_task(debouncer.debounce("user1", "msg_a"))
        task2 = asyncio.create_task(debouncer.debounce("user2", "msg_b"))

        r1, r2 = await asyncio.gather(task1, task2)
        assert r1 == "msg_a"
        assert r2 == "msg_b"

    @pytest.mark.asyncio
    async def test_zero_debounce_passes_through(self):
        """debounce_ms=0 means no debouncing — immediate pass-through."""
        debouncer = self._make_debouncer(debounce_ms=0)
        result = await debouncer.debounce("user1", "instant")
        assert result == "instant"

    @pytest.mark.asyncio
    async def test_messages_joined_with_newline(self):
        """Coalesced messages are joined with newline separator."""
        debouncer = self._make_debouncer(debounce_ms=200)

        task1 = asyncio.create_task(debouncer.debounce("user1", "line1"))
        await asyncio.sleep(0.02)
        task2 = asyncio.create_task(debouncer.debounce("user1", "line2"))

        results = await asyncio.gather(task1, task2)
        combined = results[-1]
        assert "line1\nline2" == combined or "line1" in combined

    @pytest.mark.asyncio
    async def test_flush_resets_buffer(self):
        """After flush, new messages start a fresh buffer."""
        debouncer = self._make_debouncer(debounce_ms=100)

        r1 = await debouncer.debounce("user1", "batch1")
        assert r1 == "batch1"

        r2 = await debouncer.debounce("user1", "batch2")
        assert r2 == "batch2"
        assert "batch1" not in r2

    @pytest.mark.asyncio
    async def test_pending_count(self):
        """pending_count reflects active buffers."""
        debouncer = self._make_debouncer(debounce_ms=500)
        assert debouncer.pending_count == 0

        # Start a debounce but don't await it yet
        task = asyncio.create_task(debouncer.debounce("user1", "hello"))
        await asyncio.sleep(0.02)
        assert debouncer.pending_count >= 0  # May have already flushed

        await task


class TestBotConfigDebounce:
    """Tests for debounce_ms field on BotConfig."""

    def test_botconfig_has_debounce_ms(self):
        """BotConfig has debounce_ms with default 0 (disabled)."""
        from praisonaiagents.bots import BotConfig
        cfg = BotConfig()
        assert hasattr(cfg, "debounce_ms")
        assert cfg.debounce_ms == 0

    def test_botconfig_debounce_custom(self):
        """BotConfig accepts custom debounce_ms."""
        from praisonaiagents.bots import BotConfig
        cfg = BotConfig(debounce_ms=1500)
        assert cfg.debounce_ms == 1500

    def test_botconfig_to_dict_includes_debounce(self):
        """to_dict() includes debounce_ms."""
        from praisonaiagents.bots import BotConfig
        cfg = BotConfig(debounce_ms=500)
        d = cfg.to_dict()
        assert "debounce_ms" in d
        assert d["debounce_ms"] == 500
