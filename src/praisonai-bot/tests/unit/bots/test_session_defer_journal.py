"""Issue #5152 — Defer inbound journal completion until the reply is delivered.

By default ``BotSessionManager.chat()`` marks the durable inbound journal entry
complete on the agent's clean exit — *before* the adapter delivers the reply —
so a crash in the send window loses the reply with no replay. When
``defer_journal_completion=True`` the entry is left pending and the key is
stashed so the adapter can call ``complete_last_journal_entry()`` only *after*
the reply is durably delivered. Off by default → behaviour unchanged.
"""

from __future__ import annotations

import pytest

from praisonai_bot.bots import InboundJournal
from praisonai_bot.bots._session import BotSessionManager


class _Agent:
    def __init__(self, reply: str = "answer"):
        self.chat_history = []
        self._reply = reply

    def chat(self, prompt):
        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": self._reply})
        return self._reply


class TestDeferredJournalCompletion:
    @pytest.mark.asyncio
    async def test_default_completes_on_agent_exit(self, tmp_path):
        journal = InboundJournal(path=tmp_path / "ingress.sqlite")
        mgr = BotSessionManager(platform="telegram", ingress_journal=journal)

        out = await mgr.chat(
            _Agent(), "u1", "hi", message_id="m1", account="acct"
        )

        assert out == "answer"
        # Legacy path: settled on agent completion, so a redelivery is deduped.
        assert journal.receive("telegram", "acct", "u1", "m1", {}) is None

    @pytest.mark.asyncio
    async def test_deferred_leaves_entry_pending_until_delivered(self, tmp_path):
        journal = InboundJournal(path=tmp_path / "ingress.sqlite")
        mgr = BotSessionManager(
            platform="telegram",
            ingress_journal=journal,
            defer_journal_completion=True,
        )

        out = await mgr.chat(
            _Agent(), "u1", "hi", message_id="m1", account="acct"
        )

        assert out == "answer"
        # Not yet delivered → entry stays pending (a crash here would replay).
        assert journal.pending_count() == 1

        # Adapter delivers the reply, then settles the inbound.
        assert mgr.complete_last_journal_entry() is True
        assert journal.pending_count() == 0
        # Now a redelivery is deduped.
        assert journal.receive("telegram", "acct", "u1", "m1", {}) is None

    @pytest.mark.asyncio
    async def test_deferred_entry_replayable_before_delivery(self, tmp_path):
        journal = InboundJournal(path=tmp_path / "ingress.sqlite")
        mgr = BotSessionManager(
            platform="telegram",
            ingress_journal=journal,
            defer_journal_completion=True,
        )

        await mgr.chat(_Agent(), "u1", "hi", message_id="m1", account="acct")

        # Simulate a crash before delivery: the entry is left pending (not
        # completed), so a redelivery of the same inbound is not deduped away
        # and returns the pending key for reprocessing rather than silently
        # losing the reply.
        assert journal.pending_count() == 1
        assert journal.receive("telegram", "acct", "u1", "m1", {}) is not None

    @pytest.mark.asyncio
    async def test_explicit_key_settles_only_that_turn(self, tmp_path):
        """Regression (Issue #5152): concurrent turns run under different
        per-storage-key locks, so one turn's delivery acknowledgement must
        settle *only* that turn's inbound. Passing the explicit journal key to
        ``complete_last_journal_entry`` guarantees it never settles another
        still-undelivered turn's entry.
        """
        journal = InboundJournal(path=tmp_path / "ingress.sqlite")
        mgr = BotSessionManager(
            platform="telegram",
            ingress_journal=journal,
            defer_journal_completion=True,
        )

        # Two different users → two deferred entries, both pending.
        await mgr.chat(_Agent(), "uA", "hi", message_id="mA", account="acct")
        key_a = mgr._last_journal_key
        await mgr.chat(_Agent(), "uB", "hi", message_id="mB", account="acct")
        key_b = mgr._last_journal_key

        assert key_a is not None and key_b is not None and key_a != key_b
        assert journal.pending_count() == 2

        # Turn A's reply is delivered first (out of order): settle ONLY A.
        assert mgr.complete_last_journal_entry(key_a) is True
        assert journal.pending_count() == 1
        # B is still pending/redeliverable — not clobbered by A's ack.
        assert mgr._last_journal_key == key_b
        assert journal.receive("telegram", "acct", "uB", "mB", {}) is not None

        # Now settle B.
        assert mgr.complete_last_journal_entry(key_b) is True
        assert journal.pending_count() == 0
