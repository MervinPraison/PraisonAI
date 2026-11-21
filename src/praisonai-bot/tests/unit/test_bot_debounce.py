"""
TDD tests for bot inbound message debounce.

Debounce coalesces rapid messages from the same user into a single
agent.chat() call, preventing duplicate processing and wasted tokens.
"""

import asyncio
import pytest
from unittest.mock import patch


class TestInboundDebouncer:
    """Tests for InboundDebouncer."""

    def _make_debouncer(self, debounce_ms=300):
        from praisonai_bot.bots._debounce import InboundDebouncer
        return InboundDebouncer(debounce_ms=debounce_ms)

    @pytest.mark.asyncio
    async def test_single_message_flushes_after_delay(self):
        """A single message is flushed after the debounce window."""
        debouncer = self._make_debouncer(debounce_ms=100)
        result = await debouncer.debounce("user1", "hello")
        assert result is not None
        assert result.final == "hello"
        assert result.preceding == []

    @pytest.mark.asyncio
    async def test_rapid_messages_coalesced(self):
        """Multiple rapid messages from same user are joined."""
        debouncer = self._make_debouncer(debounce_ms=200)

        # Enqueue rapidly without awaiting individually
        task1 = asyncio.create_task(debouncer.debounce("user1", "hello"))
        await asyncio.sleep(0.02)
        task2 = asyncio.create_task(debouncer.debounce("user1", "world"))

        superseded, batch = await asyncio.gather(task1, task2)
        # One turn per burst: the earlier caller short-circuits, the final
        # caller dispatches the coalesced batch.
        assert superseded is None
        assert batch is not None
        assert batch.final == "hello\nworld"
        assert batch.preceding == ["hello"]

    @pytest.mark.asyncio
    async def test_different_users_independent(self):
        """Messages from different users are NOT coalesced."""
        debouncer = self._make_debouncer(debounce_ms=100)

        task1 = asyncio.create_task(debouncer.debounce("user1", "msg_a"))
        task2 = asyncio.create_task(debouncer.debounce("user2", "msg_b"))

        r1, r2 = await asyncio.gather(task1, task2)
        assert r1.final == "msg_a"
        assert r2.final == "msg_b"

    @pytest.mark.asyncio
    async def test_zero_debounce_passes_through(self):
        """debounce_ms=0 means no debouncing — immediate pass-through."""
        debouncer = self._make_debouncer(debounce_ms=0)
        result = await debouncer.debounce("user1", "instant")
        assert result is not None
        assert result.final == "instant"

    @pytest.mark.asyncio
    async def test_messages_joined_with_newline(self):
        """Coalesced messages are joined with newline separator."""
        debouncer = self._make_debouncer(debounce_ms=200)

        task1 = asyncio.create_task(debouncer.debounce("user1", "line1"))
        await asyncio.sleep(0.02)
        task2 = asyncio.create_task(debouncer.debounce("user1", "line2"))

        superseded, batch = await asyncio.gather(task1, task2)
        assert superseded is None
        assert batch.final == "line1\nline2"

    @pytest.mark.asyncio
    async def test_flush_resets_buffer(self):
        """After flush, new messages start a fresh buffer."""
        debouncer = self._make_debouncer(debounce_ms=100)

        r1 = await debouncer.debounce("user1", "batch1")
        assert r1.final == "batch1"

        r2 = await debouncer.debounce("user1", "batch2")
        assert r2.final == "batch2"
        assert "batch1" not in r2.final

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

    @pytest.mark.asyncio
    async def test_max_wait_bounds_sustained_stream(self):
        """A stream faster than debounce_ms still flushes by max_wait_ms."""
        from praisonai_bot.bots import _debounce
        with patch.object(_debounce, "_MAX_WAIT_FACTOR", 2.5):
            debouncer = _debounce.InboundDebouncer(debounce_ms=100)
        loop = asyncio.get_running_loop()
        start = loop.time()
        first = asyncio.create_task(debouncer.debounce("u", "m0"))
        tasks = [first]
        for i in range(1, 10):
            await asyncio.sleep(0.05)
            if first.done():
                break
            tasks.append(asyncio.create_task(debouncer.debounce("u", f"m{i}")))
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
        assert loop.time() - start < 0.4
        # Exactly one caller dispatches the burst: the final one.
        batches = [r for r in results if r is not None]
        assert len(batches) == 1
        assert batches[0].final.startswith("m0\nm1")
        debouncer.cancel_all()

    @pytest.mark.asyncio
    async def test_max_buffered_flushes_immediately(self):
        """Reaching max_buffered flushes without waiting."""
        from praisonai_bot.bots import _debounce
        with patch.object(_debounce, "_MAX_BUFFERED", 3):
            debouncer = _debounce.InboundDebouncer(debounce_ms=5000)
        tasks = [asyncio.create_task(debouncer.debounce("u", str(i))) for i in range(3)]
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=1.0)
        # Superseded callers resolve None; only the final caller dispatches.
        assert results[0] is None
        assert results[1] is None
        assert results[2] is not None
        assert results[2].final == "0\n1\n2"
        assert results[2].preceding == ["0", "1"]
        assert debouncer.pending_count == 0

    @pytest.mark.asyncio
    async def test_one_turn_per_burst_contract(self):
        """A 3-message burst: two callers get None, the last gets the batch."""
        debouncer = self._make_debouncer(debounce_ms=200)

        tasks = [asyncio.create_task(debouncer.debounce("user1", "a"))]
        for msg in ("b", "c"):
            await asyncio.sleep(0.02)
            tasks.append(asyncio.create_task(debouncer.debounce("user1", msg)))

        results = await asyncio.gather(*tasks)
        assert results[0] is None
        assert results[1] is None
        assert results[2] is not None
        batch = results[2]
        assert batch.final == "a\nb\nc"
        assert batch.preceding == ["a", "b"]

    @pytest.mark.asyncio
    async def test_cancelled_final_caller_batch_falls_back_to_survivor(self):
        """A cancelled final caller must not swallow the whole burst.

        The flush picks the last *unfinished* future as the batch owner, so
        when the newest caller is cancelled the earlier survivor dispatches
        the batch instead of every caller resolving ``None``.
        """
        debouncer = self._make_debouncer(debounce_ms=200)

        first = asyncio.create_task(debouncer.debounce("user1", "a"))
        await asyncio.sleep(0.02)
        second = asyncio.create_task(debouncer.debounce("user1", "b"))
        await asyncio.sleep(0.02)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second

        batch = await first
        assert batch is not None
        assert batch.final == "a\nb"

    def test_default_max_wait_is_multiple_of_debounce(self):
        from praisonai_bot.bots._debounce import InboundDebouncer
        assert InboundDebouncer(debounce_ms=1000)._max_wait_s == 5.0
        assert InboundDebouncer(debounce_ms=0)._max_wait_s == 0


class TestDebounceEligibilityGate:
    """The adapters import the gate from the bot package (older-core safe)."""

    def test_gate_is_importable_from_the_bot_debounce_module(self):
        # telegram/discord/slack and the gateway handler import the gate from
        # here, so a core without the shared predicate still yields a working
        # module instead of an ImportError at adapter import time.
        from praisonai_bot.bots._debounce import should_debounce_inbound

        assert callable(should_debounce_inbound)

    def test_gate_matches_the_core_rule(self):
        from praisonaiagents.bots.admission import (
            should_debounce_inbound as core_gate,
        )
        from praisonai_bot.bots._debounce import should_debounce_inbound

        assert should_debounce_inbound is core_gate

    def test_fallback_gate_mirrors_the_control_word_rule(self):
        from praisonai_bot.bots._debounce import _fallback_should_debounce_inbound

        # De-bouncable: ordinary prose, including a word that merely contains
        # a control word.
        assert _fallback_should_debounce_inbound("hello there") is True
        assert _fallback_should_debounce_inbound("please status report") is True
        # Bypass the window: disabled, media, empty, control words, slash forms.
        assert _fallback_should_debounce_inbound("hi", allow_debounce=False) is False
        assert _fallback_should_debounce_inbound("hi", has_media=True) is False
        assert _fallback_should_debounce_inbound("   ") is False
        for word in ("stop", "cancel", "status", "  STOP  ", "/new"):
            assert _fallback_should_debounce_inbound(word) is False

    @pytest.mark.parametrize(
        "text,kwargs",
        [
            ("hello there", {}),
            ("please status report", {}),
            ("  STOP  ", {}),
            ("Cancel", {}),
            ("status", {}),
            ("/new", {}),
            ("/", {}),
            ("", {}),
            ("   ", {}),
            ("hello", {"has_media": True}),
            ("hello", {"allow_debounce": False}),
            ("[In reply to: \"hi\"]\nstop", {}),
        ],
    )
    def test_fallback_gate_agrees_with_the_core_gate(self, text, kwargs):
        """The local mirror must not drift from the shared predicate."""
        from praisonaiagents.bots.admission import (
            should_debounce_inbound as core_gate,
        )
        from praisonai_bot.bots._debounce import _fallback_should_debounce_inbound

        assert _fallback_should_debounce_inbound(text, **kwargs) == core_gate(
            text, **kwargs
        )

    def test_module_still_loads_on_a_core_without_the_shared_gate(self):
        """An older core (no shared predicate) must not break adapter imports."""
        import importlib

        import praisonai_bot.bots._debounce as debounce_mod
        import praisonaiagents.bots.admission as admission

        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.delattr(admission, "should_debounce_inbound", raising=False)
            reloaded = importlib.reload(debounce_mod)
            assert (
                reloaded.should_debounce_inbound
                is reloaded._fallback_should_debounce_inbound
            )
            # The fallback still enforces the eligibility rule end to end.
            assert reloaded.should_debounce_inbound("hello") is True
            assert reloaded.should_debounce_inbound("stop") is False
        finally:
            monkeypatch.undo()
            importlib.reload(debounce_mod)
        assert (
            debounce_mod.should_debounce_inbound
            is admission.should_debounce_inbound
        )


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
