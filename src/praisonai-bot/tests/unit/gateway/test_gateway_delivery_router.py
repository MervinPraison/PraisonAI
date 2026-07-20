#!/usr/bin/env python3
"""Tests for gateway scheduled/hook delivery routing through DeliveryRouter.

Issue #2624: the gateway's scheduled-job and hook/webhook delivery paths must
flow through the resilient ``DeliveryRouter`` so they gain rate-limiting,
idempotency dedup, and dead-target suppression, instead of a bare
``bot.send_message()`` call.
"""

import asyncio
import sys
import tempfile
import uuid
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


def _fresh_outbox_path() -> Path:
    """A unique SQLite path so each test's durable outbox starts empty."""
    return Path(tempfile.gettempdir()) / f"gw_outbox_{uuid.uuid4().hex}.sqlite"


def _make_gateway_with_bot(bot, *, outbox_path=None, backoff=None):
    """Build a gateway wired to ``bot`` with an isolated durable outbox.

    Issue #3231: the scheduled path now dedups through a durable
    ``OutboundQueue``. Each gateway is given a fresh SQLite file so tests do not
    contaminate each other (and so a "restart" can be simulated by pointing a
    second gateway at the *same* file). ``backoff`` defaults to zero delay so a
    failed-then-retry within one test re-sends immediately instead of waiting on
    the production backoff window.
    """
    from praisonai_bot.bots import OutboundQueue
    from praisonai_bot.bots._resilience import BackoffPolicy

    gw = WebSocketGateway()
    gw._channel_bots["telegram"] = bot
    if outbox_path is None:
        outbox_path = _fresh_outbox_path()
    gw._scheduled_outbox = OutboundQueue(
        outbox_path,
        backoff=backoff if backoff is not None else BackoffPolicy(initial_ms=0),
    )
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


# ─── Durable scheduled dedup across restart (issue #3231) ────────────


def test_scheduled_delivery_survives_restart_no_double_post():
    """A crash-and-refire across a restart does NOT re-post the result.

    Regression for issue #3231: dedup was previously a per-process LRU that is
    empty after a restart, so the exact crash window a scheduler must survive
    (fire, deliver, crash, restart, re-fire) re-posted the message. With the
    durable outbox the second, *fresh-process* gateway (new object, empty LRU,
    SAME sqlite file) finds the UNIQUE idempotency key already ``sent`` and
    suppresses the duplicate.
    """
    path = _fresh_outbox_path()
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )

    # Process 1: deliver, then "crash" (drop the gateway, keep the sqlite).
    bot1 = _RecordingBot()
    gw1 = _make_gateway_with_bot(bot1, outbox_path=path)
    asyncio.run(gw1._deliver_scheduled_result(delivery, "daily report"))
    assert bot1.sends == [("-100123", "daily report", None)]

    # Process 2: fresh gateway + fresh bot + EMPTY per-process LRU, same DB.
    bot2 = _RecordingBot()
    gw2 = _make_gateway_with_bot(bot2, outbox_path=path)
    asyncio.run(gw2._deliver_scheduled_result(delivery, "daily report"))

    # The durable UNIQUE key catches the duplicate — no re-post after restart.
    assert bot2.sends == []


def test_scheduled_delivery_after_restart_delivers_new_result():
    """After a restart a genuinely NEW result (different text) is delivered.

    Durable dedup must not swallow a distinct scheduled result: a different body
    yields a different idempotency key, so it is enqueued fresh and delivered.
    """
    path = _fresh_outbox_path()

    bot1 = _RecordingBot()
    gw1 = _make_gateway_with_bot(bot1, outbox_path=path)
    d1 = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )
    asyncio.run(gw1._deliver_scheduled_result(d1, "monday report"))
    assert bot1.sends == [("-100123", "monday report", None)]

    bot2 = _RecordingBot()
    gw2 = _make_gateway_with_bot(bot2, outbox_path=path)
    d2 = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )
    asyncio.run(gw2._deliver_scheduled_result(d2, "tuesday report"))
    assert bot2.sends == [("-100123", "tuesday report", None)]


def test_scheduled_delivery_failed_send_retries_after_restart():
    """A send that never landed before a crash is re-delivered after restart.

    If the pre-crash attempt failed (entry left non-terminal), the durable
    ledger keeps it retryable so the post-restart re-fire actually delivers it
    at-least-once — the honest recovery the issue asks for, not a silent drop.
    """
    path = _fresh_outbox_path()
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )

    # Process 1: the send raises, so the entry stays non-terminal (retryable).
    bot1 = _RecordingBot(fail_times=1)
    gw1 = _make_gateway_with_bot(bot1, outbox_path=path)
    asyncio.run(gw1._deliver_scheduled_result(delivery, "will retry"))
    assert bot1.sends == []

    # Process 2: fresh gateway, same DB — the pending entry is delivered.
    bot2 = _RecordingBot()
    gw2 = _make_gateway_with_bot(bot2, outbox_path=path)
    asyncio.run(gw2._deliver_scheduled_result(delivery, "will retry"))
    assert bot2.sends == [("-100123", "will retry", None)]


def test_scheduled_delivery_falls_back_when_outbox_unavailable(monkeypatch):
    """With no durable outbox the path still delivers via the router LRU.

    The outbox is best-effort: if it cannot be built the scheduled delivery must
    still work (and still dedup in-process) exactly as before issue #3231.
    """
    bot = _RecordingBot()
    gw = _make_gateway_with_bot(bot)
    # Force the durable store to be reported unavailable so the router-LRU
    # fallback branch is exercised.
    monkeypatch.setattr(
        type(gw), "scheduled_outbox", property(lambda self: None)
    )
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )

    async def _run():
        await gw._deliver_scheduled_result(delivery, "fallback text")
        await gw._deliver_scheduled_result(delivery, "fallback text")

    asyncio.run(_run())
    # Router LRU dedup suppresses the second same-process send.
    assert bot.sends == [("-100123", "fallback text", None)]


def test_scheduled_delivery_with_backlogged_row_uses_own_key():
    """A backlogged row in the shared outbox is sent under ITS OWN key.

    Issue #3231 regression: the shared ``scheduled_outbox`` is drained whole on
    every scheduled delivery. An earlier fix stamped this call's idempotency key
    on every drained row, so an older backlogged row was sent under the current
    key — poisoning the router LRU so the current row was later suppressed as a
    duplicate and lost. Here a first send fails (leaving a retryable row), then a
    second, distinct scheduled result fires. Both rows must reach the channel:
    the backlog under its own key and the new result under its own key.
    """
    path = _fresh_outbox_path()
    delivery = SimpleNamespace(
        channel="telegram", channel_id="-100123", thread_id=None,
        session_id="cron_job1",
    )

    # First result fails on send → its row stays retryable (non-terminal).
    bot1 = _RecordingBot(fail_times=1)
    gw1 = _make_gateway_with_bot(bot1, outbox_path=path)
    asyncio.run(gw1._deliver_scheduled_result(delivery, "backlogged report"))
    assert bot1.sends == []

    # Same DB, fresh gateway (empty LRU). A NEW result fires; draining now sees
    # BOTH the retryable backlog and the new row. Each must go out under its own
    # key so neither is suppressed as a duplicate of the other.
    bot2 = _RecordingBot()
    gw2 = _make_gateway_with_bot(bot2, outbox_path=path)
    asyncio.run(gw2._deliver_scheduled_result(delivery, "fresh report"))

    texts = sorted(text for _cid, text, _tid in bot2.sends)
    assert texts == ["backlogged report", "fresh report"]


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
