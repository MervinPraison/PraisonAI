"""Boot-time outbound reply crash-recovery (Issue #3862).

The reply path is already durable-by-default — a permanently-failed / retry-
exhausted reply is parked in the adapter's ``OutboundDLQ`` — but its crash
recovery had no boot caller, the missing symmetric counterpart to the inbound
journal's ``_replay_inbound_journal`` sweep. These tests exercise the gateway's
``_replay_outbound_dlq`` static sweep directly against a fake adapter.
"""

from __future__ import annotations

import pytest

from praisonai_bot.bots._dlq import OutboundDLQ
from praisonai_bot.gateway.server import WebSocketGateway


class _FakeBot:
    """Minimal adapter exposing the seam the sweep uses: an ``_outbound_dlq``
    and an async ``send_message(channel_id, content, reply_to=, thread_id=)``."""

    def __init__(self, dlq, *, fail=False):
        self._outbound_dlq = dlq
        self._fail = fail
        self.sent = []

    async def send_message(self, channel_id, content, reply_to=None, thread_id=None):
        if self._fail:
            raise ConnectionError("transport down")
        self.sent.append((channel_id, content, reply_to, thread_id))
        return {"ok": True}


@pytest.mark.asyncio
async def test_sweep_redelivers_parked_reply_with_marker(tmp_path):
    dlq = OutboundDLQ(path=tmp_path / "outbound.sqlite")
    await dlq.enqueue_outbound(
        platform="slack", channel_id="C1", reply_text="the answer",
        error="HTTP 503", thread_id="t1", reply_to="r1",
    )
    bot = _FakeBot(dlq)

    await WebSocketGateway._replay_outbound_dlq(bot)

    assert dlq.size() == 0
    assert len(bot.sent) == 1
    channel_id, content, reply_to, thread_id = bot.sent[0]
    assert channel_id == "C1"
    assert reply_to == "r1"
    assert thread_id == "t1"
    # Ambiguous redelivery is flagged, never silent.
    assert "the answer" in content
    assert "duplicate" in content.lower()


@pytest.mark.asyncio
async def test_sweep_keeps_reply_when_transport_still_down(tmp_path):
    dlq = OutboundDLQ(path=tmp_path / "outbound.sqlite")
    await dlq.enqueue_outbound(
        platform="slack", channel_id="C1", reply_text="answer", error="HTTP 503",
    )
    bot = _FakeBot(dlq, fail=True)

    await WebSocketGateway._replay_outbound_dlq(bot)

    # Kept for the next boot; no duplicate row created.
    assert dlq.size() == 1
    assert dlq.list()[0].attempts == 1


@pytest.mark.asyncio
async def test_sweep_noop_without_dlq(tmp_path):
    class _NoDLQBot:
        async def send_message(self, *a, **k):  # pragma: no cover
            raise AssertionError("should not be called")

    # Must not raise when the adapter has no outbound DLQ.
    await WebSocketGateway._replay_outbound_dlq(_NoDLQBot())


@pytest.mark.asyncio
async def test_sweep_noop_on_empty_dlq(tmp_path):
    dlq = OutboundDLQ(path=tmp_path / "outbound.sqlite")
    bot = _FakeBot(dlq)
    await WebSocketGateway._replay_outbound_dlq(bot)
    assert bot.sent == []
