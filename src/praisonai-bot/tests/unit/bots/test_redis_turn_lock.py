"""Issue #4655 — the distributed turn lock honours ``turn_lock.backend``.

``gateway.turn_lock.backend="redis"`` must actually serialise turns for a
resolved session across replicas, not be silently inert. These tests drive the
wrapper-side ``RedisTurnLock`` / ``build_turn_lock`` with an in-memory fake Redis
(so no server is needed) and verify:

* the factory returns a plain ``LockMap`` for the default ``local`` backend,
* it returns a ``RedisTurnLock`` for ``redis`` and serialises across two
  *independent* lock instances sharing one Redis (the cross-replica case),
* a Redis outage fails *open* (local serialisation + a degraded record) rather
  than wedging a live turn.
"""
from __future__ import annotations

import asyncio

import pytest

from praisonai_bot._lockmap import LockMap
from praisonai_bot.bots._redis_turn_lock import RedisTurnLock, build_turn_lock
from praisonaiagents.gateway import TurnLockConfig


class FakeRedis:
    """Minimal async Redis supporting SET NX PX, GET, DEL and EVAL (compare-del).

    Shared by multiple ``RedisTurnLock`` instances to model separate replicas
    talking to one Redis.
    """

    def __init__(self) -> None:
        self.store: dict = {}

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        return 1

    async def eval(self, script, numkeys, key, arg):
        if self.store.get(key) == arg:
            self.store.pop(key, None)
            return 1
        return 0


class BoomRedis:
    async def set(self, *a, **k):
        raise RuntimeError("redis down")


def test_build_turn_lock_local_returns_lockmap():
    lock = build_turn_lock(TurnLockConfig())  # default local
    assert isinstance(lock, LockMap)


def test_build_turn_lock_none_returns_lockmap():
    assert isinstance(build_turn_lock(None), LockMap)


def test_build_turn_lock_redis_without_config_degrades_to_local():
    registry_marks = []

    class Reg:
        def mark(self, owner):
            registry_marks.append(owner)

        def clear(self, *a):
            pass

    lock = build_turn_lock(
        TurnLockConfig(backend="redis"), None, degraded_registry=Reg()
    )
    # No Redis available -> fail open to a local map, and record the degradation.
    assert isinstance(lock, LockMap)
    assert registry_marks  # a degraded entry was recorded


@pytest.mark.asyncio
async def test_redis_turn_lock_serialises_across_instances():
    """Two independent RedisTurnLocks over one Redis serialise a shared key."""
    redis = FakeRedis()
    a = RedisTurnLock(redis, ttl=5.0, poll_interval=0.01)
    b = RedisTurnLock(redis, ttl=5.0, poll_interval=0.01)

    order = []

    async def worker(lock, label):
        async with lock.get("session-1"):
            order.append(f"{label}-enter")
            await asyncio.sleep(0.05)
            order.append(f"{label}-exit")

    await asyncio.gather(worker(a, "A"), worker(b, "B"))

    # Whoever ran first must fully finish before the other enters.
    assert order[0].endswith("enter")
    assert order[1].endswith("exit")
    first = order[0].split("-")[0]
    second = order[2].split("-")[0]
    assert first != second
    # Lease is released back to Redis after both turns.
    assert redis.store == {}


@pytest.mark.asyncio
async def test_redis_turn_lock_release_is_compare_and_del():
    redis = FakeRedis()
    lock = RedisTurnLock(redis, ttl=5.0, poll_interval=0.01)
    async with lock.get("k"):
        # While held, the key exists under our namespaced prefix.
        assert any("turnlock" in key or key.endswith("k") for key in redis.store)
    assert redis.store == {}


@pytest.mark.asyncio
async def test_redis_turn_lock_fails_open_on_outage():
    """A Redis outage must not wedge a turn: acquire the local lock and mark degraded."""
    marks = []

    class Reg:
        def mark(self, owner):
            marks.append(owner)

        def clear(self, *a):
            pass

    lock = RedisTurnLock(BoomRedis(), ttl=5.0, poll_interval=0.01, degraded_registry=Reg())
    async with lock.get("k"):
        pass  # must not raise, must not hang
    assert marks  # degradation surfaced
