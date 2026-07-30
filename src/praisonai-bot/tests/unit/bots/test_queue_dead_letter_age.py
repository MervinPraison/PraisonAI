#!/usr/bin/env python3
"""Tests for age-gated dead-lettering in the durable queues (Issue #3519).

A transient channel outage burns the attempt budget in well under a minute.
The durable queues must NOT permanently dead-letter such deliverable traffic:
an entry is only terminal once it is BOTH attempt-exhausted AND genuinely old.
These tests drive the real ``OutboundQueue.drain`` and ``InboundJournal.replay``
paths, forcing the age condition by back-dating the stored ``ts``.
"""

import asyncio
import time
from contextlib import closing

from praisonai_bot.bots._outbox import OutboundQueue
from praisonai_bot.bots import InboundJournal


def _read_status(queue, idempotency_key="msg-1"):
    with queue._lock, closing(queue._connect()) as conn:
        return conn.execute(
            "SELECT status FROM outbound_queue WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()[0]


def _force(queue, *, entry_id, attempts, ts):
    """Back-date an entry so the drain sees it as exhausted and (option) old."""
    with queue._lock, closing(queue._connect()) as conn:
        conn.execute(
            "UPDATE outbound_queue SET attempts=?, ts=?, last_attempt=NULL, "
            "error='connection reset by peer' WHERE id=?",
            (attempts, ts, entry_id),
        )
        conn.commit()


# ── Outbound ────────────────────────────────────────────────────────────


def test_outbound_transient_outage_not_dead_lettered(tmp_path):
    """Exhausted attempts but a young entry keeps retrying, never dead-letters."""
    async def run():
        queue = OutboundQueue(path=str(tmp_path / "outbox.sqlite"), max_attempts=5)
        key = await queue.enqueue("msg-1", "telegram:123", {"content": "hi"})
        entry_id = int(key.split(":")[-1])
        # 5 attempts burned in ~45s of outage — the classic transient case.
        _force(queue, entry_id=entry_id, attempts=5, ts=time.time() - 45)

        sender_calls = []

        async def sender(target, payload):
            sender_calls.append(target)
            return True  # channel has recovered; delivery succeeds

        succeeded, failed = await queue.drain(sender)
        # It must retry (and here succeed), NOT be dead-lettered.
        assert failed == 0
        assert succeeded == 1
        assert _read_status(queue) == "sent"

    asyncio.run(run())


def test_outbound_poison_message_dead_lettered_when_old(tmp_path):
    """Exhausted AND genuinely old -> terminal permanent_failure."""
    async def run():
        queue = OutboundQueue(path=str(tmp_path / "outbox.sqlite"), max_attempts=5)
        key = await queue.enqueue("msg-1", "telegram:123", {"content": "hi"})
        entry_id = int(key.split(":")[-1])
        _force(queue, entry_id=entry_id, attempts=5, ts=time.time() - 7 * 3600)

        async def sender(target, payload):
            raise AssertionError("dead-lettered entry must not be re-sent")

        succeeded, failed = await queue.drain(sender)
        assert succeeded == 0
        assert failed == 1
        assert _read_status(queue) == "permanent_failure"

    asyncio.run(run())


def test_outbound_min_age_zero_restores_legacy_behaviour(tmp_path):
    """Opting into min_age=0 dead-letters on attempts alone (legacy)."""
    async def run():
        queue = OutboundQueue(
            path=str(tmp_path / "outbox.sqlite"),
            max_attempts=5,
            dead_letter_min_age=0,
        )
        key = await queue.enqueue("msg-1", "telegram:123", {"content": "hi"})
        entry_id = int(key.split(":")[-1])
        _force(queue, entry_id=entry_id, attempts=5, ts=time.time())  # brand new

        async def sender(target, payload):
            raise AssertionError("legacy path dead-letters without re-send")

        succeeded, failed = await queue.drain(sender)
        assert failed == 1
        assert _read_status(queue) == "permanent_failure"

    asyncio.run(run())


# ── Inbound ─────────────────────────────────────────────────────────────


def _back_date_ingress(journal, ts):
    with journal._connect() as conn:
        conn.execute("UPDATE ingress_journal SET ts=?", (ts,))
        conn.commit()


def test_inbound_transient_outage_not_quarantined(tmp_path):
    """A young stale-claimed entry over the attempt cap replays, not quarantines."""
    journal = InboundJournal(
        path=tmp_path / "ingress.sqlite", claim_timeout=1, max_attempts=3
    )
    key = journal.receive("telegram", "bot1", "chat1", "m1", {"text": "x"})
    assert key is not None
    for _ in range(3):
        journal._claim_entry(key)  # attempts now == max_attempts
    time.sleep(1.1)  # claim goes stale
    # Entry is only seconds old -> transient outage, must replay not quarantine.
    replayed = journal.replay()
    assert replayed == 1
    assert journal.quarantined_count() == 0
    assert journal.pending_count() == 1


def test_inbound_poison_message_quarantined_when_old(tmp_path):
    """An exhausted AND old stale-claimed entry is quarantined."""
    journal = InboundJournal(
        path=tmp_path / "ingress.sqlite", claim_timeout=1, max_attempts=3
    )
    key = journal.receive("telegram", "bot1", "chat1", "poison", {"text": "x"})
    assert key is not None
    for _ in range(3):
        journal._claim_entry(key)
    time.sleep(1.1)
    _back_date_ingress(journal, time.time() - 7 * 3600)  # genuinely old
    replayed = journal.replay()
    assert replayed == 0
    assert journal.quarantined_count() == 1
    assert journal.pending_count() == 0


# ── Older-core fallback (Greptile P1) ────────────────────────────────────
# The bot's dependency floor ``praisonaiagents>=1.6.152`` admits core releases
# that predate ``AttemptAndAgeDeadLetterPolicy``. On such installs the import
# guard binds the dependency-free ``LocalDeadLetterPolicy`` instead. These
# tests force that binding and assert the age gate STILL holds — i.e. a
# transient outage is not silently reverted to attempt-only dead-lettering.


def test_local_dead_letter_policy_matches_core_semantics():
    from praisonai_bot.bots._resilience import LocalDeadLetterPolicy

    policy = LocalDeadLetterPolicy(max_attempts=5, min_age_seconds=6 * 3600)
    now = time.time()
    # Exhausted but young -> retry.
    assert policy.should_dead_letter(
        attempts=5, first_seen_epoch=now - 45, now_epoch=now
    ).dead_letter is False
    # Exhausted and old -> dead-letter.
    assert policy.should_dead_letter(
        attempts=5, first_seen_epoch=now - 7 * 3600, now_epoch=now
    ).dead_letter is True
    # Known-permanent -> immediate dead-letter regardless of age.
    assert policy.should_dead_letter(
        attempts=1, first_seen_epoch=now, now_epoch=now, error_class="credential"
    ).dead_letter is True
    # Legacy min_age=0 -> attempts alone dead-letters.
    assert LocalDeadLetterPolicy(max_attempts=5, min_age_seconds=0).should_dead_letter(
        attempts=5, first_seen_epoch=now, now_epoch=now
    ).dead_letter is True


def test_outbound_age_gate_holds_on_older_core(tmp_path, monkeypatch):
    """With core lacking the policy symbol, the queue must still age-gate."""
    import praisonai_bot.bots._outbox as outbox_mod
    from praisonai_bot.bots._resilience import LocalDeadLetterPolicy

    # Simulate praisonaiagents older than 1.6.161: the module resolved the
    # local fallback at import time.
    monkeypatch.setattr(
        outbox_mod, "AttemptAndAgeDeadLetterPolicy", LocalDeadLetterPolicy
    )

    async def run():
        queue = OutboundQueue(path=str(tmp_path / "outbox.sqlite"), max_attempts=5)
        key = await queue.enqueue("msg-1", "telegram:123", {"content": "hi"})
        entry_id = int(key.split(":")[-1])
        _force(queue, entry_id=entry_id, attempts=5, ts=time.time() - 45)

        async def sender(target, payload):
            return True

        succeeded, failed = await queue.drain(sender)
        assert failed == 0 and succeeded == 1
        assert _read_status(queue) == "sent"

    asyncio.run(run())


def test_inbound_age_gate_holds_on_older_core(tmp_path, monkeypatch):
    """Inbound quarantine also stays age-gated on an older-core install."""
    import praisonai_bot.bots._ingress as ingress_mod
    from praisonai_bot.bots._resilience import LocalDeadLetterPolicy

    monkeypatch.setattr(
        ingress_mod, "AttemptAndAgeDeadLetterPolicy", LocalDeadLetterPolicy
    )

    journal = InboundJournal(
        path=tmp_path / "ingress.sqlite", claim_timeout=1, max_attempts=3
    )
    key = journal.receive("telegram", "bot1", "chat1", "m1", {"text": "x"})
    assert key is not None
    for _ in range(3):
        journal._claim_entry(key)
    time.sleep(1.1)
    replayed = journal.replay()
    assert replayed == 1
    assert journal.quarantined_count() == 0
    assert journal.pending_count() == 1
