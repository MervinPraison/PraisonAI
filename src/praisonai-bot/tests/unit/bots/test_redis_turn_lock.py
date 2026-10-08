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

    def __init__(self, clock=None) -> None:
        self.store: dict = {}
        self._expiry: dict = {}
        self.eval_calls: list = []
        self._clock = clock or time.monotonic

    def _expire_if_stale(self, key):
        exp = self._expiry.get(key)
        if exp is not None and self._clock() >= exp:
            self.store.pop(key, None)
            self._expiry.pop(key, None)

    async def set(self, key, value, nx=False, px=None):
        self._expire_if_stale(key)
        if nx and key in self.store:
            return None
        self.store[key] = value
        if px is not None:
            self._expiry[key] = self._clock() + (px / 1000.0)
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
        self._expiry[key] = self._clock() + (px / 1000.0)
        return 1

    async def eval(self, script, numkeys, key, *args):
        self.eval_calls.append((script, key, args))
        self._expire_if_stale(key)
        arg = args[0]
        if "pexpire" in script:
            if self.store.get(key) == arg:
                self._expiry[key] = self._clock() + (int(args[1]) / 1000.0)
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


@pytest.mark.parametrize("ttl", [0, -1, -0.001])
def test_redis_turn_lock_rejects_nonpositive_ttl(ttl):
    """Invalid lease lifetimes fail before acquisition or renewal can start."""
    redis = FakeRedis()
    with pytest.raises(ValueError, match="ttl must be positive"):
        RedisTurnLock(redis, ttl=ttl)
    assert redis.store == {}
    assert redis.eval_calls == []


@pytest.mark.parametrize("ttl", [0.001, 0.03, 0.06, 60])
def test_redis_turn_lock_preserves_positive_ttl(ttl):
    """Small positive lifetimes retain the existing configured expiry contract."""
    lock = RedisTurnLock(FakeRedis(), ttl=ttl)
    assert lock._ttl == ttl


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
async def test_redis_turn_lock_renews_lease_during_long_turn(monkeypatch):
    """A turn longer than ttl keeps the lease via owner-checked renewal."""
    from types import SimpleNamespace
    from praisonai_bot.bots import _redis_turn_lock

    now = [0.0]
    redis = FakeRedis(clock=lambda: now[0])

    async def advance_clock(delay):
        now[0] += delay
        await asyncio.sleep(0)

    # Advance only this module's renewal sleeps and the fake Redis TTL clock.
    # The event loop retains its real clock, so runner pauses cannot expire
    # a 60 ms test lease before the renewal task gets CPU time.
    monkeypatch.setattr(_redis_turn_lock, 'asyncio', SimpleNamespace(
        sleep=advance_clock, ensure_future=asyncio.ensure_future,
        CancelledError=asyncio.CancelledError,
    ))
    lock = RedisTurnLock(redis, ttl=0.06, poll_interval=0.01)
    async with lock.get("k"):
        (redis_key,) = list(redis.store)
        first = redis.store[redis_key]

        async def wait_for_renewals():
            while len(redis.eval_calls) < 12 or now[0] <= 3 * lock._ttl:
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_for_renewals(), timeout=5)
        assert now[0] > 3 * lock._ttl
        # GET applies expiry too; stale dictionary contents cannot pass.
        assert await redis.get(redis_key) == first


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
@pytest.mark.parametrize('ttl,poll_interval', [(0.03, 0.05), (0.03, 0.5), (0.3, 0.05)])
async def test_renewal_keeps_owner_when_acquisition_poll_is_slow(monkeypatch, ttl, poll_interval):
    """Waiting replicas' polling cadence must not make the holder renew too late."""
    import sys
    from types import SimpleNamespace
    from praisonai_bot.bots import _redis_turn_lock

    now = [0.0]
    # Only this fake Redis uses virtual time; the event-loop clock is unchanged.
    monkeypatch.setattr(sys.modules[__name__], 'time', SimpleNamespace(monotonic=lambda: now[0]))
    redis = FakeRedis()

    async def advance_clock(delay):
        now[0] += delay
        await asyncio.sleep(0)

    monkeypatch.setattr(_redis_turn_lock, 'asyncio', SimpleNamespace(
        sleep=advance_clock, ensure_future=asyncio.ensure_future,
        CancelledError=asyncio.CancelledError,
    ))
    lock = RedisTurnLock(redis, ttl=ttl, poll_interval=poll_interval)
    async with lock.get('session'):
        (key,) = list(redis.store)
        owner = redis.store[key]

        async def wait_for_renewals():
            while len(redis.eval_calls) < 12:
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_for_renewals(), timeout=5)
        assert now[0] > 3 * ttl
        assert await redis.get(key) == owner


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
