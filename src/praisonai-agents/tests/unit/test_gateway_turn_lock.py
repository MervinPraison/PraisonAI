"""Unit tests for cluster-wide per-turn serialisation (Issue #3643).

Covers the pure, core-side turn-lock contract: the ``TurnLockProtocol`` and
``TurnLeaseToken``, the zero-cost in-process ``LocalTurnLock`` default (which
must serialise turns per session and be byte-for-byte backward compatible), and
the ``TurnLockConfig`` selector wired into ``GatewayConfig``.
"""

import asyncio

import pytest

from praisonaiagents.gateway import (
    GatewayConfig,
    LocalTurnLock,
    TurnLeaseToken,
    TurnLockConfig,
    TurnLockProtocol,
)


def test_local_turn_lock_protocol_conformance():
    assert isinstance(LocalTurnLock(), TurnLockProtocol)


def test_turn_lock_config_defaults_are_local_and_disabled():
    cfg = TurnLockConfig()
    assert cfg.backend == "local"
    assert cfg.enabled is False


def test_turn_lock_config_redis_is_enabled():
    cfg = TurnLockConfig(backend="redis", ttl=30.0)
    assert cfg.enabled is True
    assert cfg.ttl == 30.0


def test_turn_lock_config_rejects_unknown_backend():
    with pytest.raises(ValueError):
        TurnLockConfig(backend="bogus")


def test_turn_lock_config_rejects_non_positive_ttl():
    with pytest.raises(ValueError):
        TurnLockConfig(ttl=0)


def test_turn_lock_config_rejects_nan_ttl():
    # NaN is not a positive lease duration; it must be rejected, not silently
    # forwarded to a distributed backend as an unusable expiry.
    with pytest.raises(ValueError):
        TurnLockConfig(ttl=float("nan"))


def test_turn_lock_config_hides_url_in_to_dict():
    cfg = TurnLockConfig(backend="redis", url="redis://secret@host:6379")
    assert cfg.to_dict()["url"] == "***"
    assert TurnLockConfig().to_dict()["url"] is None


def test_turn_lock_config_from_dict_roundtrip():
    assert TurnLockConfig.from_dict(None).backend == "local"
    cfg = TurnLockConfig.from_dict({"backend": "redis", "ttl": 5})
    assert cfg.backend == "redis"
    assert cfg.ttl == 5.0


def test_turn_lock_config_from_dict_tolerates_explicit_nulls():
    # Explicit YAML nulls (``backend:`` / ``ttl:`` with no value) fall back to
    # defaults instead of raising ``TypeError``/``ValueError``.
    cfg = TurnLockConfig.from_dict({"backend": None, "ttl": None})
    assert cfg.backend == "local"
    assert cfg.ttl == 60.0


def test_gateway_config_has_local_turn_lock_by_default():
    cfg = GatewayConfig()
    assert cfg.turn_lock.backend == "local"
    assert cfg.to_dict()["turn_lock"]["backend"] == "local"


def test_gateway_config_parses_turn_lock_from_yaml_dict():
    from praisonaiagents.gateway import MultiChannelGatewayConfig

    parsed = MultiChannelGatewayConfig.from_dict(
        {"gateway": {"turn_lock": {"backend": "redis", "ttl": 45}}}
    )
    assert parsed.gateway.turn_lock.backend == "redis"
    assert parsed.gateway.turn_lock.ttl == 45.0


def test_acquire_returns_lease_token():
    lock = LocalTurnLock()

    async def run():
        token = await lock.acquire("s", owner="r1", ttl=60.0)
        assert isinstance(token, TurnLeaseToken)
        assert token.key == "s"
        assert token.owner == "r1"
        await lock.release(token)

    asyncio.run(run())


def test_release_is_idempotent():
    lock = LocalTurnLock()

    async def run():
        token = await lock.acquire("s", owner="r1", ttl=60.0)
        await lock.release(token)
        # A second release must be a harmless no-op, never an error.
        await lock.release(token)

    asyncio.run(run())


def test_stale_token_release_does_not_free_a_new_holder():
    # Identity-checked release: a stale token from a prior owner must never
    # release the lease a *different* owner has since acquired for the same key,
    # otherwise two turns would run concurrently on one session.
    lock = LocalTurnLock()

    async def run():
        first = await lock.acquire("sess", owner="r1", ttl=60.0)
        await lock.release(first)
        second = await lock.acquire("sess", owner="r2", ttl=60.0)
        # Releasing the stale first token is a no-op; r2's lease stays held.
        await lock.release(first)
        assert lock._lock_for("sess").locked() is True
        # The rightful owner can still release cleanly.
        await lock.release(second)
        assert lock._lock_for("sess").locked() is False

    asyncio.run(run())


def test_local_turn_lock_serialises_same_session():
    # Deterministic (no timing): hold the first turn open until the second
    # worker has *attempted* to acquire, proving the same-session turns can
    # never interleave regardless of event-loop scheduling.
    lock = LocalTurnLock()
    order = []
    second_attempted = asyncio.Event()

    async def first():
        async with lock.hold("sess", owner="r1", ttl=60.0):
            order.append(("start", 1))
            await second_attempted.wait()
            order.append(("end", 1))

    async def second():
        second_attempted.set()
        async with lock.hold("sess", owner="r2", ttl=60.0):
            order.append(("start", 2))
            order.append(("end", 2))

    async def run():
        await asyncio.gather(first(), second())

    asyncio.run(run())

    # The first turn fully completes before the second begins.
    assert order == [("start", 1), ("end", 1), ("start", 2), ("end", 2)], order


def test_local_turn_lock_allows_concurrent_distinct_sessions():
    # Deterministic (no timing, 3.10-safe): worker "a" enters its lease and
    # waits for "b" to also enter before either exits. If distinct keys were
    # wrongly serialised, "b" could never enter and the wait_for would time out.
    lock = LocalTurnLock()
    a_inside = asyncio.Event()
    b_inside = asyncio.Event()
    running = 0
    max_concurrent = 0

    async def worker(key, entered, other_entered):
        nonlocal running, max_concurrent
        async with lock.hold(key, owner="r", ttl=60.0):
            running += 1
            max_concurrent = max(max_concurrent, running)
            entered.set()
            await other_entered.wait()
            running -= 1

    async def run():
        await asyncio.wait_for(
            asyncio.gather(
                worker("a", a_inside, b_inside),
                worker("b", b_inside, a_inside),
            ),
            timeout=5.0,
        )

    asyncio.run(run())
    # Different sessions do not block each other.
    assert max_concurrent == 2


def test_hold_releases_on_exception():
    lock = LocalTurnLock()

    async def run():
        with pytest.raises(RuntimeError):
            async with lock.hold("s", owner="r", ttl=60.0):
                raise RuntimeError("boom")
        # Lock must be re-acquirable after an exception inside the block.
        async with lock.hold("s", owner="r", ttl=60.0):
            pass

    asyncio.run(run())
