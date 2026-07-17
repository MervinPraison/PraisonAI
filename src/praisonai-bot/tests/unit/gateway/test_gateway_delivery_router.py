#!/usr/bin/env python3
"""Tests for gateway scheduled/hook delivery routing through DeliveryRouter.

Issue #2624: the gateway's scheduled-job and hook/webhook delivery paths must
flow through the resilient ``DeliveryRouter`` so they gain rate-limiting,
idempotency dedup, and dead-target suppression, instead of a bare
``bot.send_message()`` call.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonai_bot.gateway.server import WebSocketGateway


class _RecordingBot:
    """Channel bot stub that records every send and can fail on demand."""

    def __init__(self, fail_times: int = 0):
        self.sends = []
        self._fail_times = fail_times

    async def send_message(self, channel_id, text, thread_id=None):
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("boom")
        self.sends.append((channel_id, text, thread_id))
        return {"ok": True}


def _make_gateway_with_bot(bot):
    gw = WebSocketGateway()
    gw._channel_bots["telegram"] = bot
    return gw


def test_scheduled_delivery_routes_through_router():
    """A scheduled result is delivered via the router to the channel bot."""
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )

    asyncio.run(gw._deliver_scheduled_result(delivery, "daily report"))

    assert gw.delivery_router is not None
    assert bot.sends == [("-100123", "daily report", None)]


def test_scheduled_delivery_dedupes_refired_job():
    """A re-fired job (same target + same text) does not double-post."""
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )

    asyncio.run(gw._deliver_scheduled_result(delivery, "same text"))
    asyncio.run(gw._deliver_scheduled_result(delivery, "same text"))

    assert len(bot.sends) == 1  # second send suppressed by idempotency guard


def test_scheduled_delivery_preserves_thread_id():
    """A threaded scheduled delivery still carries the thread id."""
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id="42",
        session_id="cron_job1",
    )

    asyncio.run(gw._deliver_scheduled_result(delivery, "threaded"))

    assert bot.sends == [("-100123", "threaded", "42")]


def test_scheduled_delivery_dedupes_refired_threaded_job():
    """A re-fired *threaded* job is deduplicated by the shared router LRU.

    Regression for issue #2624: the threaded path must not build a throw-away
    router (whose empty LRU never dedups) — it records/checks the idempotency
    key on the shared router so a re-fire cannot double-post.
    """
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id="42",
        session_id="cron_job1",
    )

    asyncio.run(gw._deliver_scheduled_result(delivery, "same threaded text"))
    asyncio.run(gw._deliver_scheduled_result(delivery, "same threaded text"))

    assert bot.sends == [("-100123", "same threaded text", "42")]


def test_scheduled_delivery_failed_threaded_send_stays_retryable():
    """A failed *threaded* send does not record the key, so a retry re-sends."""
    bot = _RecordingBot(fail_times=1)
    gw = _make_gateway_with_bot(bot)
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id="42",
        session_id="cron_job1",
    )

    asyncio.run(gw._deliver_scheduled_result(delivery, "retry threaded"))
    asyncio.run(gw._deliver_scheduled_result(delivery, "retry threaded"))

    assert bot.sends == [("-100123", "retry threaded", "42")]


def test_scheduled_delivery_failed_send_stays_retryable():
    """A failed send does not record the idempotency key, so retry re-sends."""
    bot = _RecordingBot(fail_times=1)
    gw = _make_gateway_with_bot(bot)
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )

    # First call fails (send raises), second call must actually deliver.
    asyncio.run(gw._deliver_scheduled_result(delivery, "retry me"))
    asyncio.run(gw._deliver_scheduled_result(delivery, "retry me"))

    assert bot.sends == [("-100123", "retry me", None)]


def test_hook_reply_routes_through_router():
    """A hook reply is delivered via the router and reports success."""
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)

    delivered = asyncio.run(gw._deliver_hook_reply("telegram:-100999", "hook hi"))

    assert delivered is True
    assert bot.sends == [("-100999", "hook hi", None)]


def test_hook_reply_dedupes_duplicate():
    """A duplicate hook reply (same target + text) is deduplicated."""
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)

    d1 = asyncio.run(gw._deliver_hook_reply("telegram:-100999", "dup"))
    d2 = asyncio.run(gw._deliver_hook_reply("telegram:-100999", "dup"))

    assert d1 is True and d2 is True
    assert len(bot.sends) == 1


def test_hook_reply_case_insensitive_channel():
    """A mixed-case channel resolves to the registered lowercase bot."""
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)

    delivered = asyncio.run(gw._deliver_hook_reply("Telegram:-100999", "hi"))

    assert delivered is True
    assert bot.sends == [("-100999", "hi", None)]


def test_scheduled_delivery_missing_target_is_skipped():
    """A delivery with no channel/channel_id is skipped without error."""
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)
    delivery = SimpleNamespace(channel="", channel_id="", thread_id=None)

    asyncio.run(gw._deliver_scheduled_result(delivery, "nope"))

    assert bot.sends == []


# ─── DeliveryRouter thread routing (issue #3141) ─────────────────────


class _NoThreadBot:
    """Adapter whose ``send_message`` has no ``thread_id`` parameter."""

    def __init__(self):
        self.sends = []

    async def send_message(self, channel_id, text):
        self.sends.append((channel_id, text))
        return {"ok": True}


class _RouterBotOS:
    def __init__(self, bot):
        self._bot = bot

    def get_bot(self, platform):
        return self._bot

    def list_bots(self):
        return ["telegram"]


def _make_router(bot):
    from praisonai_bot.bots.delivery import DeliveryRouter

    return DeliveryRouter(_RouterBotOS(bot))


def test_resolve_parses_thread_segment():
    """``platform:channel:thread`` resolves to a 3-tuple keeping the thread."""
    router = _make_router(_RecordingBot())
    assert router.resolve("telegram:-100123:789") == ("telegram", "-100123", "789")


def test_resolve_without_thread_returns_none_thread():
    """``platform:channel`` resolves with ``thread_id`` of ``None``."""
    router = _make_router(_RecordingBot())
    assert router.resolve("telegram:-100123") == ("telegram", "-100123", None)


def test_deliver_routes_into_thread():
    """A threaded target passes ``thread_id`` through to ``send_message``."""
    bot = _RecordingBot()
    router = _make_router(bot)

    ok = asyncio.run(router.deliver("telegram:-100123:789", "hi thread"))

    assert ok is True
    assert bot.sends == [("-100123", "hi thread", "789")]


def test_deliver_without_thread_omits_thread_id():
    """A non-threaded target still sends with ``thread_id=None``."""
    bot = _RecordingBot()
    router = _make_router(bot)

    ok = asyncio.run(router.deliver("telegram:-100123", "no thread"))

    assert ok is True
    assert bot.sends == [("-100123", "no thread", None)]


def test_deliver_thread_ignored_for_adapter_without_thread_support():
    """A thread target does not break an adapter lacking ``thread_id``."""
    bot = _NoThreadBot()
    router = _make_router(bot)

    ok = asyncio.run(router.deliver("telegram:-100123:789", "legacy adapter"))

    assert ok is True
    assert bot.sends == [("-100123", "legacy adapter")]
