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


def test_dead_letter_count(tmp_path):
    """dead_letter_count() reports only the permanent_failure tier (Issue #4265)."""
    async def run():
        q = _new_queue(tmp_path)
        assert q.dead_letter_count() == 0
        # A live pending entry is not dead-letter.
        await q.enqueue("m-pending", "telegram:1", {"content": "a"})
        assert q.dead_letter_count() == 0
        # Force one entry into the dead-letter tier.
        key = await q.enqueue("m-dead", "telegram:2", {"content": "b"})
        entry_id = int(key.split(":")[-1])
        with q._lock, closing(q._connect()) as conn:
            conn.execute(
                "UPDATE outbound_queue SET status='permanent_failure' WHERE id=?",
                (entry_id,),
            )
            conn.commit()
        assert q.dead_letter_count() == 1
        assert q.pending_count() == 1  # the dead entry is not counted as pending

    asyncio.run(run())


def test_try_depth_snapshot_matches_blocking_counts(tmp_path):
    """try_depth_snapshot() returns the same (pending, dead) as the blocking APIs (Issue #4265)."""
    async def run():
        q = _new_queue(tmp_path)
        assert q.try_depth_snapshot() == (0, 0)
        await q.enqueue("m-pending", "telegram:1", {"content": "a"})
        key = await q.enqueue("m-dead", "telegram:2", {"content": "b"})
        entry_id = int(key.split(":")[-1])
        with q._lock, closing(q._connect()) as conn:
            conn.execute(
                "UPDATE outbound_queue SET status='permanent_failure' WHERE id=?",
                (entry_id,),
            )
            conn.commit()
        snap = q.try_depth_snapshot()
        assert snap == (q.pending_count(), q.dead_letter_count()) == (1, 1)

    asyncio.run(run())


def test_try_depth_snapshot_never_blocks_on_held_lock(tmp_path):
    """A contended writer lock yields None immediately rather than blocking (Issue #4265).

    The gateway health/metrics surface runs on the event loop; it must never
    wait on the outbox writer lock. When the lock is held the non-blocking
    snapshot returns None so the caller can reuse its last-known depths.
    """
    q = _new_queue(tmp_path)
    q._lock.acquire()
    try:
        assert q.try_depth_snapshot() is None
    finally:
        q._lock.release()
    # Once released, the snapshot works again.
    assert q.try_depth_snapshot() == (0, 0)


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


def test_recovery_annotator_labels_unreconciled_resend(tmp_path):
    """An unreconciled recovered entry is labelled by recovery_annotator."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []

        async def sender(target, payload):
            sent.append(payload)
            return True

        def annotator(entry, payload):
            assert entry.idempotency_key == "msg-1"
            out = dict(payload)
            out["content"] = "[recovered] " + payload.get("content", "")
            return out

        succeeded, failed = await q2.drain(sender, recovery_annotator=annotator)

        assert (succeeded, failed) == (1, 0)
        assert len(sent) == 1
        assert sent[0]["content"] == "[recovered] hi"

    asyncio.run(run())


def test_recovery_annotator_skipped_when_reconciled(tmp_path):
    """A reconciled entry is not re-sent, so the annotator never fires."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []
        annotated = []

        async def sender(target, payload):
            sent.append(payload)
            return True

        async def reconciler(entry):
            return True  # confirmed already delivered

        def annotator(entry, payload):
            annotated.append(entry.idempotency_key)
            return payload

        succeeded, failed = await q2.drain(
            sender, reconciler=reconciler, recovery_annotator=annotator
        )

        assert (succeeded, failed) == (1, 0)
        assert sent == []  # no re-dispatch
        assert annotated == []  # annotator never consulted

    asyncio.run(run())


def test_recovery_annotator_not_applied_to_fresh_entries(tmp_path):
    """Fresh pending entries are sent verbatim, never annotated."""
    async def run():
        q = _new_queue(tmp_path)
        await q.enqueue("msg-fresh", "telegram:123", {"content": "hi"})

        sent = []

        def annotator(entry, payload):
            out = dict(payload)
            out["content"] = "LABELLED " + payload.get("content", "")
            return out

        async def sender(target, payload):
            sent.append(payload)
            return True

        succeeded, failed = await q.drain(sender, recovery_annotator=annotator)

        assert (succeeded, failed) == (1, 0)
        assert sent[0]["content"] == "hi"  # untouched

    asyncio.run(run())


def test_durable_delivery_marks_recovered_resend(tmp_path):
    """DurableDelivery(mark_recovered=True) prefixes an unreconciled re-send."""
    from praisonai_bot.bots._delivery import DurableDelivery, RECOVERED_PREFIX

    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        # Enqueue via DurableDelivery-style payload and force in-flight.
        key = await q1.enqueue(
            "msg-1",
            "telegram:123",
            {"content": "hello", "kwargs": {}, "idempotency_key": "msg-1"},
        )
        entry_id = int(key.split(":")[-1])
        with q1._lock, closing(q1._connect()) as conn:
            conn.execute(
                "UPDATE outbound_queue SET status='sending' WHERE id=?",
                (entry_id,),
            )
            conn.commit()

        q2 = OutboundQueue(path=str(path))

        received = []

        class _Adapter:
            async def send_message(self, channel_id, content, **kwargs):
                received.append(content)
                return True

        delivery = DurableDelivery(
            q2, _Adapter(), platform="telegram", mark_recovered=True
        )
        succeeded, failed = await delivery.drain_pending()

        assert (succeeded, failed) == (1, 0)
        assert len(received) == 1
        assert received[0].startswith(RECOVERED_PREFIX)
        assert received[0].endswith("hello")

    asyncio.run(run())


def test_recovery_annotator_mutation_then_raise_sends_unlabelled(tmp_path):
    """An annotator that mutates its dict then raises must not leak a partial label.

    The annotator receives its own fresh copy, so the send falls back to the
    original unlabelled payload rather than a half-mutated one.
    """
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []

        async def sender(target, payload):
            sent.append(payload)
            return True

        def annotator(entry, payload):
            payload["content"] = "MUTATED " + payload.get("content", "")
            raise RuntimeError("annotator blew up after mutating")

        succeeded, failed = await q2.drain(sender, recovery_annotator=annotator)

        assert (succeeded, failed) == (1, 0)
        assert len(sent) == 1
        assert sent[0]["content"] == "hi"  # original, not the mutated copy

    asyncio.run(run())


def test_recovery_annotator_non_dict_return_sends_unlabelled(tmp_path):
    """An annotator returning a non-dict is rejected; the original is sent."""
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []

        async def sender(target, payload):
            sent.append(payload)
            return True

        def annotator(entry, payload):
            return "not a dict"

        succeeded, failed = await q2.drain(sender, recovery_annotator=annotator)

        assert (succeeded, failed) == (1, 0)
        assert sent[0]["content"] == "hi"

    asyncio.run(run())


def test_recovered_label_survives_transient_resend_failure(tmp_path):
    """A recovered send that fails transiently stays labelled on the next retry.

    First drain: send raises a recoverable error -> the entry must remain
    'recovered' (not demoted to 'failed'). Second drain: send succeeds and the
    recovery_annotator still labels the copy, so no unlabelled duplicate escapes.
    """
    async def run():
        path = tmp_path / "outbox.sqlite"
        q1 = OutboundQueue(path=str(path))
        await _seed_in_flight(q1)

        q2 = OutboundQueue(path=str(path))

        sent = []
        attempts = {"n": 0}

        async def sender(target, payload):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ConnectionError("transient network blip")
            sent.append(payload)
            return True

        def annotator(entry, payload):
            out = dict(payload)
            out["content"] = "[recovered] " + payload.get("content", "")
            return out

        # First drain: transient failure keeps the entry recovered.
        s1, f1 = await q2.drain(sender, recovery_annotator=annotator)
        assert (s1, f1) == (0, 1)
        assert sent == []
        assert _read_status(q2) == "recovered"

        # Clear the backoff gate so the retry is eligible immediately.
        with q2._lock, closing(q2._connect()) as conn:
            conn.execute(
                "UPDATE outbound_queue SET last_attempt=NULL WHERE idempotency_key='msg-1'"
            )
            conn.commit()

        # Second drain: succeeds AND is still labelled.
        s2, f2 = await q2.drain(sender, recovery_annotator=annotator)
        assert (s2, f2) == (1, 0)
        assert len(sent) == 1
        assert sent[0]["content"] == "[recovered] hi"

    asyncio.run(run())


def test_status_for_reports_entry_state(tmp_path):
    """``status_for`` returns the current status, or None for an unknown key."""
    async def run():
        q = _new_queue(tmp_path)
        assert q.status_for("msg-1") is None  # not enqueued yet

        key = await q.enqueue("msg-1", "telegram:123", {"content": "hi"})
        assert q.status_for("msg-1") == "pending"

        await q.mark_sent(key)
        assert q.status_for("msg-1") == "sent"

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
