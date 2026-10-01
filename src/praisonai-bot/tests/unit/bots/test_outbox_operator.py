#!/usr/bin/env python3
"""
Tests for the operator inspect/retry/purge surface on the durable outbound
queue (Issue #5366), giving parity with the inbound DLQ CLI.

Covers ``OutboundQueue.list`` (with status/target filters), ``stats``,
``retry`` (requeue a failed/permanent entry for the next drain), and
``purge_entry`` (targeted single-entry delete).
"""

import asyncio

from praisonai_bot.bots._outbox import OutboundQueue


def test_list_returns_enqueued_entries(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        await q.enqueue("m1", "telegram:1", {"text": "a"})
        await q.enqueue("m2", "slack:C0", {"text": "b"})
        entries = q.list()
        assert {e.idempotency_key for e in entries} == {"m1", "m2"}
        assert all(e.status == "pending" for e in entries)

    asyncio.run(run())


def test_list_filters_by_status_and_target(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        k1 = await q.enqueue("m1", "telegram:1", {"text": "a"})
        await q.enqueue("m2", "slack:C0", {"text": "b"})
        await q.mark_failed(k1, "boom", permanent=True)

        failed = q.list(status="permanent_failure")
        assert [e.idempotency_key for e in failed] == ["m1"]

        by_target = q.list(target="slack:C0")
        assert [e.idempotency_key for e in by_target] == ["m2"]

        assert q.list(status="pending", target="slack:C0")[0].idempotency_key == "m2"

    asyncio.run(run())


def test_stats_counts_per_status(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        k1 = await q.enqueue("m1", "telegram:1", {"text": "a"})
        await q.enqueue("m2", "telegram:2", {"text": "b"})
        await q.mark_failed(k1, "boom", permanent=True)

        stats = q.stats()
        assert stats.get("pending") == 1
        assert stats.get("permanent_failure") == 1

    asyncio.run(run())


def test_retry_requeues_permanent_failure(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        key = await q.enqueue("m1", "telegram:1", {"text": "a"})
        await q.mark_failed(key, "boom", permanent=True)
        assert q.stats().get("permanent_failure") == 1

        assert await q.retry(key) is True
        entry = q.list()[0]
        assert entry.status == "pending"
        assert entry.attempts == 0
        assert entry.error is None

        # Second retry is a no-op (already pending, not terminal-failed).
        assert await q.retry(key) is False

    asyncio.run(run())


def test_retry_unknown_key_returns_false(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        assert await q.retry("telegram:1:999") is False

    asyncio.run(run())


def test_purge_entry_removes_single_entry(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        key = await q.enqueue("m1", "telegram:1", {"text": "a"})
        await q.enqueue("m2", "telegram:2", {"text": "b"})

        assert q.purge_entry(key) is True
        remaining = q.list()
        assert [e.idempotency_key for e in remaining] == ["m2"]

        assert q.purge_entry(key) is False

    asyncio.run(run())


def test_retried_entry_drains_successfully(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        key = await q.enqueue("m1", "telegram:1", {"text": "a"})
        await q.mark_failed(key, "chat unavailable", permanent=True)

        await q.retry(key)

        sent = []

        async def sender(target, payload):
            sent.append((target, payload))
            return True

        succeeded, failed = await q.drain(sender)
        assert succeeded == 1 and failed == 0
        assert sent == [("telegram:1", {"text": "a"})]
        assert q.list(status="sent")[0].idempotency_key == "m1"

    asyncio.run(run())


def test_retry_does_not_touch_recovered_entry(tmp_path):
    """A crash-recovered entry must keep its 'recovered' safeguard; manual retry
    is a no-op so the next drain still reconciles/annotates it (no unlabelled
    duplicate)."""

    async def run():
        path = tmp_path / "o.sqlite"
        q1 = OutboundQueue(path=str(path))
        key = await q1.enqueue("m1", "telegram:1", {"text": "a"})
        # Simulate an in-flight send interrupted by a crash: leave it 'sending'.
        with q1._lock, __import__("contextlib").closing(q1._connect()) as conn:
            conn.execute(
                "UPDATE outbound_queue SET status = 'sending' WHERE id = ?",
                (q1._extract_id_from_key(key),),
            )
            conn.commit()
        # Reopen: crash recovery flips 'sending' -> 'recovered'.
        q2 = OutboundQueue(path=str(path))
        assert q2.list()[0].status == "recovered"

        assert await q2.retry(key) is False
        assert q2.list()[0].status == "recovered"

    asyncio.run(run())


def test_purge_refuses_in_flight_sending_entry(tmp_path):
    """purge_entry must not delete a row an active send is awaiting a terminal
    write on."""

    async def run():
        path = tmp_path / "o.sqlite"
        q = OutboundQueue(path=str(path))
        key = await q.enqueue("m1", "telegram:1", {"text": "a"})
        with q._lock, __import__("contextlib").closing(q._connect()) as conn:
            conn.execute(
                "UPDATE outbound_queue SET status = 'sending' WHERE id = ?",
                (q._extract_id_from_key(key),),
            )
            conn.commit()

        assert q.purge_entry(key) is False
        assert q.list()[0].status == "sending"

    asyncio.run(run())


def test_targeted_ops_reject_mismatched_key(tmp_path):
    """A key whose id exists but whose target/idempotency differ must not mutate
    the real entry (stale/mistyped key protection)."""

    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        key = await q.enqueue("m1", "telegram:1", {"text": "a"})
        await q.mark_failed(key, "boom", permanent=True)
        entry_id = q._extract_id_from_key(key)

        wrong_key = f"telegram:999:wrong:{entry_id}"
        assert await q.retry(wrong_key) is False
        assert q.purge_entry(wrong_key) is False
        # Real entry untouched and still actionable via its true key.
        assert q.list()[0].status == "permanent_failure"
        assert await q.retry(key) is True

    asyncio.run(run())


def test_read_only_does_not_recover_sending_rows(tmp_path):
    """Opening the outbox read_only (operator inspection) must NOT flip live
    'sending' rows to 'recovered' — doing so would let a running drain re-claim
    and duplicate an in-flight message."""

    async def run():
        path = tmp_path / "o.sqlite"
        q = OutboundQueue(path=str(path))
        key = await q.enqueue("m1", "telegram:1", {"text": "a"})
        with q._lock, __import__("contextlib").closing(q._connect()) as conn:
            conn.execute(
                "UPDATE outbound_queue SET status = 'sending' WHERE id = ?",
                (q._extract_id_from_key(key),),
            )
            conn.commit()

        ro = OutboundQueue(path=str(path), read_only=True)
        assert ro.list()[0].status == "sending"
        assert ro.stats().get("sending") == 1

    asyncio.run(run())
