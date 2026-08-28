"""Issue #4541 — durable, restart-safe delivery idempotency on every path.

The lightweight ``SchedulerDelivery`` / standalone tick previously relied on the
router's in-process LRU, which is empty after a restart — so a job re-fired
across a crash could double-post. These tests verify that injecting the same
durable ``SqliteIdempotencyStore`` the gateway uses makes the router's proactive
dedup restart-safe: a re-fired job with a stable key is suppressed even by a
*fresh* router instance (simulating a process restart), and a failed send
releases the durable reservation so it stays retryable.
"""

from __future__ import annotations

import asyncio

from praisonai_bot.bots._idempotency import SqliteIdempotencyStore
from praisonai_bot.bots.delivery import DeliveryRouter


def _make_router(store, *, fail=False):
    """Build a DeliveryRouter over a fake BotOS recording every send."""
    sent = []

    class FakeBot:
        async def send_message(self, channel_id, text):
            if fail:
                raise RuntimeError("boom")
            sent.append((channel_id, text))

    class FakeBotOS:
        def get_bot(self, platform):
            return FakeBot()

        def list_bots(self):
            return ["telegram"]

    router = DeliveryRouter(FakeBotOS(), idempotency_store=store)
    router.directory._home_channels = {}
    router.directory._aliases = {}
    router.directory._observed = {}
    router.directory.set_home_channel("telegram", "123")
    return router, sent


def test_durable_dedup_survives_restart(tmp_path):
    db = tmp_path / "delivery.db"
    key = "sched:j1:telegram:123::abc"

    store1 = SqliteIdempotencyStore(db)
    router1, sent1 = _make_router(store1)
    assert asyncio.run(
        router1.deliver("telegram:123", "hello", idempotency_key=key)
    ) is True
    assert sent1 == [("123", "hello")]

    # Simulate a process restart: a brand-new store + router over the SAME db
    # file. The in-process LRU is empty, but the durable store remembers the
    # key, so the re-fired job is suppressed instead of double-posting.
    store2 = SqliteIdempotencyStore(db)
    router2, sent2 = _make_router(store2)
    assert asyncio.run(
        router2.deliver("telegram:123", "hello", idempotency_key=key)
    ) is True
    assert sent2 == []  # duplicate suppressed across the restart


def test_failed_send_releases_reservation(tmp_path):
    db = tmp_path / "delivery.db"
    key = "sched:j1:telegram:123::abc"

    # First attempt fails: the durable reservation must be released so a retry
    # is not deduplicated against its own crashed attempt.
    store = SqliteIdempotencyStore(db)
    router_fail, _ = _make_router(store, fail=True)
    assert asyncio.run(
        router_fail.deliver("telegram:123", "hello", idempotency_key=key)
    ) is False

    # Retry (fresh router, same durable store/db) now succeeds — the released
    # reservation let it through rather than being wrongly suppressed.
    store2 = SqliteIdempotencyStore(db)
    router_ok, sent = _make_router(store2)
    assert asyncio.run(
        router_ok.deliver("telegram:123", "hello", idempotency_key=key)
    ) is True
    assert sent == [("123", "hello")]


def test_no_store_falls_back_to_lru(tmp_path):
    # Without an injected store the router keeps its bounded in-process LRU: a
    # duplicate is suppressed within the process, exactly as before.
    router, sent = _make_router(None)
    key = "k1"
    assert asyncio.run(router.deliver("telegram:123", "hi", idempotency_key=key))
    assert asyncio.run(router.deliver("telegram:123", "hi", idempotency_key=key))
    assert sent == [("123", "hi")]  # second suppressed in-process
