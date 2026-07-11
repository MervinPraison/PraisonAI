#!/usr/bin/env python3
"""
Tests for per-conversation (per-lane) outbound delivery ordering.

Under ``ordering="strict"`` the durable outbox must deliver messages to the
same conversation (lane) in FIFO order: an earlier undelivered message must
block later same-lane messages until it reaches ``sent`` or
``permanent_failure``. Different lanes still drain in parallel. Under the
default ``ordering="best_effort"`` the historic global-order behaviour is
preserved for backward compatibility.
"""

import asyncio
from contextlib import closing

import pytest

from praisonai_bot.bots._outbox import OutboundQueue
from praisonai_bot.bots._reliability import resolve_reliability


def _read_status(queue, idempotency_key):
    with queue._lock, closing(queue._connect()) as conn:
        row = conn.execute(
            "SELECT status FROM outbound_queue WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()
        return row[0] if row else None


def test_default_ordering_is_best_effort(tmp_path):
    q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
    assert q.ordering == "best_effort"


def test_invalid_ordering_rejected(tmp_path):
    with pytest.raises(ValueError):
        OutboundQueue(path=str(tmp_path / "o.sqlite"), ordering="bogus")


def test_lane_key_defaults_to_target(tmp_path):
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"))
        await q.enqueue("m1", "telegram:1", {"text": "a"})
        with q._lock, closing(q._connect()) as conn:
            lane = conn.execute(
                "SELECT lane_key FROM outbound_queue WHERE idempotency_key='m1'"
            ).fetchone()[0]
        assert lane == "telegram:1"

    asyncio.run(run())


def test_strict_holds_later_same_lane_until_head_sent(tmp_path):
    """Later same-lane entries are not offered while the head is undelivered."""
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"), ordering="strict")
        await q.enqueue("a", "telegram:1", {"text": "first"})
        await q.enqueue("b", "telegram:1", {"text": "second"})

        pending = q._get_pending_entries()
        keys = [e.idempotency_key for e in pending]
        assert keys == ["a"], f"only head of lane should be offered, got {keys}"

    asyncio.run(run())


def test_strict_transient_failure_does_not_let_second_overtake(tmp_path):
    """If the head fails transiently, the second same-lane msg must not send."""
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"), ordering="strict")
        await q.enqueue("a", "telegram:1", {"text": "first"})
        await q.enqueue("b", "telegram:1", {"text": "second"})

        delivered = []

        async def sender(target, payload):
            # Fail the first message transiently; succeed anything else.
            if payload["text"] == "first":
                return False
            delivered.append(payload["text"])
            return True

        await q.drain(sender)
        # 'second' must NOT have been delivered because the head 'first' failed.
        assert delivered == []
        assert _read_status(q, "a") == "failed"
        assert _read_status(q, "b") == "pending"

    asyncio.run(run())


def test_strict_second_flows_after_head_sent(tmp_path):
    """Once the head is sent, the next same-lane entry becomes eligible."""
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"), ordering="strict")
        await q.enqueue("a", "telegram:1", {"text": "first"})
        await q.enqueue("b", "telegram:1", {"text": "second"})

        order = []

        async def sender(target, payload):
            order.append(payload["text"])
            return True

        # First drain sends the head only.
        await q.drain(sender)
        # Second drain now sees 'b' as the new head.
        await q.drain(sender)

        assert order == ["first", "second"]
        assert _read_status(q, "a") == "sent"
        assert _read_status(q, "b") == "sent"

    asyncio.run(run())


def test_strict_different_lanes_drain_in_parallel(tmp_path):
    """Heads of distinct lanes are all offered together."""
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"), ordering="strict")
        await q.enqueue("a1", "telegram:1", {"text": "l1-first"})
        await q.enqueue("a2", "telegram:1", {"text": "l1-second"})
        await q.enqueue("b1", "telegram:2", {"text": "l2-first"})

        pending = {e.idempotency_key for e in q._get_pending_entries()}
        # Head of each lane offered; l1's second is held.
        assert pending == {"a1", "b1"}

    asyncio.run(run())


def test_best_effort_allows_overtake(tmp_path):
    """Best-effort mode offers all pending entries (no lane gate)."""
    async def run():
        q = OutboundQueue(path=str(tmp_path / "o.sqlite"), ordering="best_effort")
        await q.enqueue("a", "telegram:1", {"text": "first"})
        await q.enqueue("b", "telegram:1", {"text": "second"})

        keys = {e.idempotency_key for e in q._get_pending_entries()}
        assert keys == {"a", "b"}

    asyncio.run(run())


def test_reliability_production_selects_strict():
    r = resolve_reliability("production")
    assert r.outbound_ordering == "strict"


def test_reliability_default_and_off_stay_best_effort():
    assert resolve_reliability(None).outbound_ordering == "best_effort"
    assert resolve_reliability("default").outbound_ordering == "best_effort"
    assert resolve_reliability("off").outbound_ordering == "best_effort"


def test_reliability_explicit_ordering_wins():
    # Explicit best_effort overrides production's strict default.
    r = resolve_reliability("production", outbound_ordering="best_effort")
    assert r.outbound_ordering == "best_effort"
    # Explicit strict can be opted into on a non-production preset.
    r2 = resolve_reliability("default", outbound_ordering="strict")
    assert r2.outbound_ordering == "strict"


def test_reliability_invalid_ordering_rejected():
    with pytest.raises(ValueError):
        resolve_reliability("production", outbound_ordering="bogus")


def test_legacy_db_migrates_lane_key(tmp_path):
    """Opening a pre-lane DB backfills lane_key = target."""
    import sqlite3

    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE outbound_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            target TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            metadata TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER DEFAULT 0,
            last_attempt REAL,
            error TEXT,
            sent_at REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO outbound_queue(ts, idempotency_key, target, status) "
        "VALUES (1.0, 'old', 'telegram:9', 'pending')"
    )
    conn.commit()
    conn.close()

    q = OutboundQueue(path=str(path), ordering="strict")
    with q._lock, closing(q._connect()) as c:
        lane = c.execute(
            "SELECT lane_key FROM outbound_queue WHERE idempotency_key='old'"
        ).fetchone()[0]
    assert lane == "telegram:9"
    # And it is offered as its lane head under strict ordering.
    assert [e.idempotency_key for e in q._get_pending_entries()] == ["old"]


def test_setup_durable_delivery_forwards_ordering(tmp_path):
    """The durable adapter mixin must propagate ``ordering`` into the outbox.

    Regression guard: ``resolve_reliability('production')`` resolves to
    ``strict`` but that value is worthless unless the outbox construction path
    honours it. This asserts the wiring so ``production`` genuinely enforces
    per-lane FIFO instead of silently staying best-effort.
    """
    from praisonai_bot.bots._durable_adapter import DurableAdapterMixin

    class _Adapter(DurableAdapterMixin):
        pass

    # Default keeps historic best-effort behaviour.
    a = _Adapter()
    a.setup_durable_delivery(outbox_path=str(tmp_path / "d.sqlite"), platform="telegram")
    assert a.outbox is not None
    assert a.outbox.ordering == "best_effort"

    # Explicit / preset-driven strict ordering is forwarded to the queue.
    b = _Adapter()
    b.setup_durable_delivery(
        outbox_path=str(tmp_path / "s.sqlite"),
        platform="telegram",
        ordering=resolve_reliability("production").outbound_ordering,
    )
    assert b.outbox is not None
    assert b.outbox.ordering == "strict"
