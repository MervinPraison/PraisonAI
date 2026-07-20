#!/usr/bin/env python3
"""
Tests for effectively-once delivery on the Slack adapter (issue #3185).

The outbox's crash-reconciliation seam was shipped but unused: no channel
adapter implemented ``was_delivered`` / declared ``reconciles_unknown_send``,
so every channel fell back to at-least-once (a duplicate on restart). Slack can
read back recent channel history and match a client-side idempotency key
stamped into the message ``metadata``, so it opts into effectively-once
delivery. These tests cover:

  * the adapter declares the capability and implements was_delivered();
  * send_message stamps the idempotency key into Slack metadata;
  * was_delivered() matches (and only matches) that key in history;
  * the DurableDelivery drain wires the reconciler so a recovered entry that
    already landed is NOT re-sent.
"""

import asyncio
from contextlib import closing

import pytest

from praisonai_bot.bots._delivery import DurableDelivery
from praisonai_bot.bots._outbox import OutboundQueue


class _FakeSlackClient:
    """Minimal stand-in for slack_sdk AsyncWebClient used by the adapter."""

    def __init__(self):
        self.sent = []  # captured chat_postMessage kwargs
        self.history = []  # messages returned by conversations_history

    async def chat_postMessage(self, **kwargs):
        self.sent.append(kwargs)
        # Mirror what a real send would leave in channel history.
        self.history.insert(
            0,
            {"ts": f"ts-{len(self.sent)}", "metadata": kwargs.get("metadata")},
        )
        return {"ts": f"ts-{len(self.sent)}"}

    async def conversations_history(self, **kwargs):
        return {"messages": list(self.history)}

    async def conversations_replies(self, **kwargs):
        return {"messages": list(self.history)}


class _MissingScopeClient(_FakeSlackClient):
    """Slack client that rejects ``metadata`` unless the scope is granted."""

    async def chat_postMessage(self, **kwargs):
        if kwargs.get("metadata"):
            raise Exception("missing_scope: metadata.message:write required")
        return await super().chat_postMessage(**kwargs)


def _make_slack_bot(client):
    from praisonai_bot.bots.slack import SlackBot

    bot = SlackBot(token="xoxb-test")
    bot._client = client
    return bot


def test_slack_declares_reconcile_capability():
    from praisonai_bot.bots.slack import SlackBot

    caps = SlackBot.default_capabilities()
    assert caps.reconciles_unknown_send is True


def test_send_message_stamps_idempotency_metadata():
    async def run():
        client = _FakeSlackClient()
        bot = _make_slack_bot(client)
        await bot.send_message("C123", "hi", idempotency_key="key-1")
        assert client.sent, "message was not sent"
        meta = client.sent[0].get("metadata")
        assert meta is not None
        assert meta["event_type"] == "praisonai_outbound"
        assert meta["event_payload"]["idempotency_key"] == "key-1"

    asyncio.run(run())


def test_was_delivered_matches_key_in_history():
    async def run():
        client = _FakeSlackClient()
        bot = _make_slack_bot(client)
        await bot.send_message("C123", "hi", idempotency_key="key-1")

        assert await bot.was_delivered("slack:C123", "key-1") is True
        assert await bot.was_delivered("slack:C123", "other-key") is False

    asyncio.run(run())


def test_was_delivered_false_without_metadata():
    async def run():
        client = _FakeSlackClient()
        bot = _make_slack_bot(client)
        # A plain send (no idempotency key) leaves no matching metadata.
        await bot.send_message("C123", "hi")
        assert await bot.was_delivered("slack:C123", "key-1") is False

    asyncio.run(run())


def _read_status(queue, idempotency_key):
    with queue._lock, closing(queue._connect()) as conn:
        return conn.execute(
            "SELECT status FROM outbound_queue WHERE idempotency_key=?",
            (idempotency_key,),
        ).fetchone()[0]


def test_drain_reconciles_recovered_entry_without_resend(tmp_path):
    """A recovered entry whose send already landed is not re-sent via Slack."""

    async def run():
        path = tmp_path / "outbox.sqlite"
        client = _FakeSlackClient()
        bot = _make_slack_bot(client)

        # Pretend the prior (pre-crash) send already landed in Slack history.
        client.history.insert(
            0,
            {
                "ts": "ts-prior",
                "metadata": {
                    "event_type": "praisonai_outbound",
                    "event_payload": {"idempotency_key": "key-1"},
                },
            },
        )

        # Seed an in-flight ('sending') entry, then simulate a restart.
        q1 = OutboundQueue(path=str(path))
        await q1.enqueue(
            "key-1",
            "slack:C123",
            {"content": "hi", "kwargs": {}, "idempotency_key": "key-1"},
        )
        with q1._lock, closing(q1._connect()) as conn:
            conn.execute("UPDATE outbound_queue SET status='sending'")
            conn.commit()

        q2 = OutboundQueue(path=str(path))
        delivery = DurableDelivery(q2, bot, platform="slack")

        succeeded, failed = await delivery.drain_pending()

        assert succeeded == 1
        assert failed == 0
        assert client.sent == []  # effectively-once: no duplicate send
        assert _read_status(q2, "key-1") == "sent"

    asyncio.run(run())


def test_drain_resends_when_prior_send_not_found(tmp_path):
    """A recovered entry with no matching history is re-sent (at-least-once)."""

    async def run():
        path = tmp_path / "outbox.sqlite"
        client = _FakeSlackClient()
        bot = _make_slack_bot(client)

        q1 = OutboundQueue(path=str(path))
        await q1.enqueue(
            "key-2",
            "slack:C123",
            {"content": "hi", "kwargs": {}, "idempotency_key": "key-2"},
        )
        with q1._lock, closing(q1._connect()) as conn:
            conn.execute("UPDATE outbound_queue SET status='sending'")
            conn.commit()

        q2 = OutboundQueue(path=str(path))
        delivery = DurableDelivery(q2, bot, platform="slack")

        succeeded, failed = await delivery.drain_pending()

        assert succeeded == 1
        assert failed == 0
        assert len(client.sent) == 1  # re-sent exactly once
        # The re-send re-stamps the key so a future reconcile can confirm it.
        assert (
            client.sent[0]["metadata"]["event_payload"]["idempotency_key"] == "key-2"
        )

    asyncio.run(run())


def test_send_falls_back_when_metadata_scope_missing():
    """A missing metadata scope must degrade to at-least-once, not lose the msg."""

    async def run():
        client = _MissingScopeClient()
        bot = _make_slack_bot(client)
        msg = await bot.send_message("C123", "hi", idempotency_key="key-1")
        # Delivered (at-least-once) even though metadata was rejected.
        assert msg.message_id
        assert len(client.sent) == 1
        assert client.sent[0].get("metadata") is None

    asyncio.run(run())


def test_was_delivered_uses_replies_for_threaded_send():
    """Threaded sends are reconciled via conversations.replies, not history."""

    async def run():
        client = _FakeSlackClient()
        bot = _make_slack_bot(client)
        # Simulate a threaded reply that landed with our metadata. It must be
        # found even though conversations.history would exclude thread replies.
        client.history.insert(
            0,
            {
                "ts": "ts-reply",
                "metadata": {
                    "event_type": "praisonai_outbound",
                    "event_payload": {"idempotency_key": "key-t"},
                },
            },
        )
        assert (
            await bot.was_delivered("slack:C123", "key-t", thread_id="1.0") is True
        )

    asyncio.run(run())


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            if "tmp_path" in fn.__code__.co_varnames:
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"PASS {name}")
    print("All Slack reconcile tests passed")
