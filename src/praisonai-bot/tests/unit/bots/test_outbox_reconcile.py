#!/usr/bin/env python3
"""
Tests for effectively-once outbound delivery via crash reconciliation.

A crash after a message is handed to the channel API but before its terminal
status is recorded leaves the entry in the ``sending`` state. On restart the
queue moves such entries to ``recovered`` and, when a reconciler is supplied,
confirms whether the prior attempt landed before re-dispatching — avoiding
duplicate channel messages.
"""

import asyncio
from contextlib import closing

from praisonai_bot.bots._outbox import OutboundQueue


def _new_queue(tmp_path, name="outbox.sqlite"):
    return OutboundQueue(path=str(tmp_path / name))


def _read_status(queue, idempotency_key="msg-1"):
    with queue._lock, closing(queue._connect()) as conn:
        return conn.execute(
            "SELECT status FROM outbound_queue WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()[0]


async def _seed_in_flight(queue):
    """Enqueue a message and force it into the in-flight 'sending' state."""
    key = await queue.enqueue("msg-1", "telegram:123", {"content": "hi"})
    entry_id = int(key.split(":")[-1])
    with queue._lock, closing(queue._connect()) as conn:
        conn.execute(
            "UPDATE outbound_queue SET status='sending' WHERE id=?",
            (entry_id,),
        )
        conn.commit()
    return key


def test_crash_recovers_sending_to_recovered(tmp_path):
    """A 'sending' entry from a prior crash becomes 'recovered' on restart."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        # Simulate restart: new instance re-runs the schema/recovery step
        q2 = OutboundQueue(path=str(path))
        assert _read_status(q2) == "recovered"

    asyncio.run(run())


def test_reconciler_skips_resend_when_already_delivered(tmp_path):
    """If the reconciler confirms delivery, the message is NOT re-sent."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []

        async def sender(target, payload):
            sent.append((target, payload))
            return True

        async def reconciler(entry):
            assert entry.idempotency_key == "msg-1"
            return True  # prior attempt landed

        succeeded, failed = await q2.drain(sender, reconciler=reconciler)

        assert succeeded == 1
        assert failed == 0
        assert sent == []  # effectively-once: no duplicate send
        assert _read_status(q2) == "sent"

    asyncio.run(run())


def test_reconciler_resends_when_not_delivered(tmp_path):
    """If the reconciler reports not delivered, the message IS re-sent."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []

        async def sender(target, payload):
            sent.append((target, payload))
            return True

        async def reconciler(entry):
            return False  # prior attempt did not land

        succeeded, failed = await q2.drain(sender, reconciler=reconciler)

        assert succeeded == 1
        assert failed == 0
        assert len(sent) == 1  # re-sent exactly once

    asyncio.run(run())


def test_no_reconciler_falls_back_to_at_least_once(tmp_path):
    """Without a reconciler, recovered entries are re-sent (at-least-once)."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []

        async def sender(target, payload):
            sent.append((target, payload))
            return True

        succeeded, failed = await q2.drain(sender)

        assert succeeded == 1
        assert failed == 0
        assert len(sent) == 1  # at-least-once re-send

    asyncio.run(run())


def test_reconciler_only_applies_to_recovered_entries(tmp_path):
    """Fresh pending entries are sent normally, never reconciled."""
    async def run():
        q = _new_queue(tmp_path)
        await q.enqueue("msg-fresh", "telegram:123", {"content": "hi"})

        sent = []

        async def sender(target, payload):
            sent.append((target, payload))
            return True

        reconciler_calls = []

        async def reconciler(entry):
            reconciler_calls.append(entry.idempotency_key)
            return True

        succeeded, failed = await q.drain(sender, reconciler=reconciler)

        assert succeeded == 1
        assert failed == 0
        assert len(sent) == 1  # pending entry sent normally
        assert reconciler_calls == []  # reconciler never consulted

    asyncio.run(run())


def test_reconciler_failure_falls_back_to_resend(tmp_path):
    """A reconciler that raises falls back to an at-least-once re-send."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []

        async def sender(target, payload):
            sent.append((target, payload))
            return True

        async def reconciler(entry):
            raise RuntimeError("provider lookup unavailable")

        succeeded, failed = await q2.drain(sender, reconciler=reconciler)

        assert succeeded == 1
        assert failed == 0
        assert len(sent) == 1  # fell back to re-send

    asyncio.run(run())


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
            print(f"PASS {name}")
    print("All reconcile tests passed")
