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
