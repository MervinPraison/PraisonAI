"""Tests for durable inbound message journal (crash-safe bot ingress)."""
from __future__ import annotations

import time

import pytest


class TestInboundJournalReceive:
    def test_duplicate_completed_returns_none(self, tmp_path):
        from praisonai_bot.bots import InboundJournal

        journal = InboundJournal(path=tmp_path / "ingress.sqlite")
        key = journal.receive("telegram", "bot1", "chat1", "msg1", {"text": "hi"})
        assert key is not None

        journal.complete(key)
        assert journal.receive("telegram", "bot1", "chat1", "msg1", {"text": "hi"}) is None

    def test_duplicate_pending_returns_key_for_retry(self, tmp_path):
        from praisonai_bot.bots import InboundJournal

        journal = InboundJournal(path=tmp_path / "ingress.sqlite")
        first = journal.receive("telegram", "bot1", "chat1", "msg1", {"text": "hi"})
        assert first is not None

        second = journal.receive("telegram", "bot1", "chat1", "msg1", {"text": "hi"})
        assert second == first

    def test_duplicate_active_claim_returns_none(self, tmp_path):
        from praisonai_bot.bots import InboundJournal

        journal = InboundJournal(path=tmp_path / "ingress.sqlite", claim_timeout=300)
        key = journal.receive("slack", "bot1", "chan1", "msg42", {})
        assert key is not None

        with journal.claim(key):
            assert journal.receive("slack", "bot1", "chan1", "msg42", {}) is None

    def test_duplicate_stale_claim_returns_key(self, tmp_path):
        from praisonai_bot.bots import InboundJournal

        journal = InboundJournal(path=tmp_path / "ingress.sqlite", claim_timeout=1)
        key = journal.receive("discord", "bot1", "chan1", "msg99", {})
        assert key is not None

        with journal.claim(key):
            pass

        time.sleep(1.1)
        retry = journal.receive("discord", "bot1", "chan1", "msg99", {})
        assert retry == key


class TestBotSessionManagerIngress:
    @pytest.mark.asyncio
    async def test_chat_completes_journal_entry(self, tmp_path):
        from unittest.mock import Mock

        from praisonai_bot.bots import InboundJournal
        from praisonai_bot.bots._session import BotSessionManager

        journal = InboundJournal(path=tmp_path / "ingress.sqlite")
        mgr = BotSessionManager(platform="telegram", ingress_journal=journal)

        agent = Mock()
        agent.chat_history = []
        agent.chat = Mock(return_value="ok")

        response = await mgr.chat(
            agent,
            user_id="user1",
            prompt="hello",
            chat_id="chat1",
            message_id="mid-1",
            account="bot1",
        )

        assert response == "ok"
        assert journal.pending_count() == 0
        assert journal.receive("telegram", "bot1", "chat1", "mid-1", {}) is None
