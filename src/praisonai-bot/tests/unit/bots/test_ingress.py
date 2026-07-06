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


class TestInboundJournalQuarantine:
    def test_replay_caps_attempts_and_quarantines(self, tmp_path):
        from praisonai_bot.bots import InboundJournal

        journal = InboundJournal(
            path=tmp_path / "ingress.sqlite", claim_timeout=1, max_attempts=3
        )
        key = journal.receive("telegram", "bot1", "chat1", "poison", {"text": "x"})
        assert key is not None

        # Simulate 3 crash-interrupted claims (attempts increment each time,
        # entry left in a stale 'claimed' state as after a SIGTERM).
        for _ in range(3):
            journal._claim_entry(key)
        time.sleep(1.1)

        # attempts now >= max_attempts and entry is stale-claimed.
        replayed = journal.replay()
        assert replayed == 0
        assert journal.quarantined_count() == 1
        assert journal.pending_count() == 0

    def test_replay_resets_when_under_cap(self, tmp_path):
        from praisonai_bot.bots import InboundJournal

        journal = InboundJournal(
            path=tmp_path / "ingress.sqlite", claim_timeout=1, max_attempts=5
        )
        key = journal.receive("telegram", "bot1", "chat1", "msg1", {"text": "x"})
        assert key is not None

        journal._claim_entry(key)  # attempts = 1
        time.sleep(1.1)

        replayed = journal.replay()
        assert replayed == 1
        assert journal.quarantined_count() == 0
        assert journal.pending_count() == 1

    def test_replay_routes_to_dlq(self, tmp_path):
        from praisonai_bot.bots import InboundDLQ, InboundJournal

        dlq = InboundDLQ(path=tmp_path / "dlq.sqlite")
        journal = InboundJournal(
            path=tmp_path / "ingress.sqlite",
            claim_timeout=1,
            max_attempts=1,
            dlq=dlq,
        )
        key = journal.receive(
            "telegram", "bot1", "chat1", "poison",
            {"text": "boom", "user_id": "user9"},
        )
        assert key is not None

        journal._claim_entry(key)  # attempts = 1 >= max_attempts
        time.sleep(1.1)

        assert journal.replay() == 0
        assert journal.quarantined_count() == 1
        assert dlq.size() == 1
        entry = dlq.list(limit=1)[0]
        assert entry.user_id == "user9"
        assert entry.prompt == "boom"
        assert "Max inbound attempts exceeded" in entry.error

    def test_quarantined_not_reoffered_on_redelivery(self, tmp_path):
        from praisonai_bot.bots import InboundJournal

        journal = InboundJournal(
            path=tmp_path / "ingress.sqlite", claim_timeout=1, max_attempts=1
        )
        key = journal.receive("telegram", "bot1", "chat1", "poison", {"text": "x"})
        assert key is not None

        journal._claim_entry(key)
        time.sleep(1.1)
        journal.replay()
        assert journal.quarantined_count() == 1

        # Webhook redelivery must not reprocess a quarantined poison message.
        assert journal.receive("telegram", "bot1", "chat1", "poison", {"text": "x"}) is None


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
