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
import time

import pytest

from praisonai_bot._lockmap import LockMap
from praisonai_bot.bots._redis_turn_lock import RedisTurnLock, build_turn_lock
from praisonaiagents.gateway import TurnLockConfig


class FakeRedis:
    """Minimal async Redis supporting SET NX PX, GET, DEL, PEXPIRE and EVAL.

    Models per-key TTL expiry (``px``) so a lease that is never renewed becomes
    reclaimable, and shared by multiple ``RedisTurnLock`` instances to model
    separate replicas talking to one Redis.
    """

    def __init__(self) -> None:
        self.store: dict = {}
        self._expiry: dict = {}
        self.eval_calls: list = []

    def _expire_if_stale(self, key):
        exp = self._expiry.get(key)
        if exp is not None and time.monotonic() >= exp:
            self.store.pop(key, None)
            self._expiry.pop(key, None)

    async def set(self, key, value, nx=False, px=None):
        self._expire_if_stale(key)
        if nx and key in self.store:
            return None
        self.store[key] = value
        if px is not None:
            self._expiry[key] = time.monotonic() + (px / 1000.0)
        else:
            self._expiry.pop(key, None)
        return True

    async def get(self, key):
        self._expire_if_stale(key)
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)
        self._expiry.pop(key, None)
        return 1

    async def pexpire(self, key, px):
        self._expire_if_stale(key)
        if key not in self.store:
            return 0
        self._expiry[key] = time.monotonic() + (px / 1000.0)
        return 1

    async def eval(self, script, numkeys, key, *args):
        self.eval_calls.append((script, key, args))
        self._expire_if_stale(key)
        arg = args[0]
        if "pexpire" in script:
            if self.store.get(key) == arg:
                self._expiry[key] = time.monotonic() + (int(args[1]) / 1000.0)
                return 1
            return 0
        # compare-and-del
        if self.store.get(key) == arg:
            self.store.pop(key, None)
            self._expiry.pop(key, None)
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
async def test_redis_turn_lock_release_leaves_other_owner_key():
    """Release is owner-checked: a lease reclaimed by another replica survives."""
    redis = FakeRedis()
    lock = RedisTurnLock(redis, ttl=5.0, poll_interval=0.01)
    async with lock.get("k"):
        # Simulate another replica reclaiming the expired lease mid-turn.
        (redis_key,) = list(redis.store)
        redis.store[redis_key] = "other-owner-token"
    # Our compare-and-del must NOT delete a key we no longer own.
    assert redis.store.get(redis_key) == "other-owner-token"
    # And the release went through the atomic EVAL path.
    assert redis.eval_calls


@pytest.mark.asyncio
async def test_redis_turn_lock_renews_lease_during_long_turn():
    """A turn longer than ttl keeps the lease via owner-checked renewal."""
    redis = FakeRedis()
    lock = RedisTurnLock(redis, ttl=0.06, poll_interval=0.01)
    async with lock.get("k"):
        (redis_key,) = list(redis.store)
        first = redis.store[redis_key]
        # Run well past ttl; without renewal the key would expire and vanish.
        await asyncio.sleep(0.2)
        assert redis.store.get(redis_key) == first  # still ours


@pytest.mark.asyncio
async def test_redis_turn_lock_reclaims_expired_lease():
    """An unrenewed, expired lease becomes reclaimable (no permanent wedge)."""
    redis = FakeRedis()
    a = RedisTurnLock(redis, ttl=0.05, poll_interval=0.01)
    # Manually plant an expiring lease from a "crashed" holder.
    redis_key = a._redis_key("k")
    await redis.set(redis_key, "dead-holder", nx=True, px=50)
    b = RedisTurnLock(redis, ttl=5.0, poll_interval=0.01)
    # b must be able to acquire once the dead holder's lease expires.
    async with b.get("k"):
        assert redis.store.get(redis_key) != "dead-holder"


@pytest.mark.asyncio
async def test_redis_turn_lock_fails_open_and_serialises_on_outage():
    """A Redis outage must not wedge a turn and must still serialise in-process."""
    marks = []

    class Reg:
        def mark(self, owner):
            marks.append(owner)

        def clear(self, *a):
            pass

    lock = RedisTurnLock(BoomRedis(), ttl=5.0, poll_interval=0.01, degraded_registry=Reg())

    events = []

    async def worker(label):
        async with lock.get("k"):
            events.append(f"{label}-enter")
            await asyncio.sleep(0.03)
            events.append(f"{label}-exit")

    await asyncio.gather(worker("A"), worker("B"))

    # Even with Redis down, the local lock serialises the two turns.
    assert events[0].endswith("enter")
    assert events[1].endswith("exit")
    assert events[0].split("-")[0] != events[2].split("-")[0]
    assert marks  # degradation surfaced
