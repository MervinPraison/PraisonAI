"""Concurrency properties of DualLock (async/sync shared-mutex semantics)."""
import asyncio
import threading
import time

import pytest

from praisonaiagents.agent.async_safety import DualLock


def test_nested_async_then_sync_does_not_deadlock():
    """The handoff seeding path holds ``async_lock()`` then takes ``sync()``.

    With a shared mutex, the inner sync acquire on the event-loop thread must be
    treated as re-entrant (the async side registered that thread as owner),
    otherwise it self-deadlocks against the mutex it already holds.
    """
    lock = DualLock()

    async def _exercise():
        async with lock.async_lock():
            # Nested sync acquire on the same (event-loop) thread must not block.
            with lock.sync():
                return "ok"

    result = asyncio.run(asyncio.wait_for(_exercise(), timeout=5))
    assert result == "ok"


def test_sync_and_async_are_mutually_exclusive():
    """Holding the sync side must exclude a concurrent async acquire."""
    lock = DualLock()
    order = []

    def _hold_sync(started, release):
        with lock.sync():
            order.append("sync-in")
            started.set()
            release.wait(5)
            order.append("sync-out")

    async def _exercise():
        started = threading.Event()
        release = threading.Event()
        t = threading.Thread(target=_hold_sync, args=(started, release))
        t.start()
        assert started.wait(5)

        # The async acquire must not complete until the sync holder releases.
        acquired = asyncio.Event()

        async def _try_async():
            async with lock.async_lock():
                order.append("async-in")
                acquired.set()

        task = asyncio.create_task(_try_async())
        await asyncio.sleep(0.2)
        assert not acquired.is_set(), "async acquired while sync held the mutex"

        release.set()
        await asyncio.wait_for(task, timeout=5)
        t.join(5)

    asyncio.run(_exercise())
    assert order == ["sync-in", "sync-out", "async-in"]


def test_async_wait_does_not_block_event_loop():
    """While an async caller waits on the mutex, other coroutines still run."""
    lock = DualLock()

    def _hold_sync(started, release):
        with lock.sync():
            started.set()
            release.wait(5)

    async def _exercise():
        started = threading.Event()
        release = threading.Event()
        t = threading.Thread(target=_hold_sync, args=(started, release))
        t.start()
        assert started.wait(5)

        ticked = []

        async def _ticker():
            for _ in range(3):
                ticked.append(time.monotonic())
                await asyncio.sleep(0.05)

        async def _waiter():
            async with lock.async_lock():
                return "done"

        waiter = asyncio.create_task(_waiter())
        await asyncio.wait_for(_ticker(), timeout=5)
        # The loop kept ticking even though _waiter is blocked on the mutex.
        assert len(ticked) == 3

        release.set()
        assert await asyncio.wait_for(waiter, timeout=5) == "done"
        t.join(5)

    asyncio.run(_exercise())


def test_sync_is_reentrant_same_thread():
    """Nested ``sync()`` on one thread must not self-deadlock."""
    lock = DualLock()
    with lock.sync():
        with lock.sync():
            assert True
