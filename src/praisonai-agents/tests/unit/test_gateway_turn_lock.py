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


def test_turn_lock_config_hides_url_in_to_dict():
    cfg = TurnLockConfig(backend="redis", url="redis://secret@host:6379")
    assert cfg.to_dict()["url"] == "***"
    assert TurnLockConfig().to_dict()["url"] is None


def test_turn_lock_config_from_dict_roundtrip():
    assert TurnLockConfig.from_dict(None).backend == "local"
    cfg = TurnLockConfig.from_dict({"backend": "redis", "ttl": 5})
    assert cfg.backend == "redis"
    assert cfg.ttl == 5.0


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


def test_local_turn_lock_serialises_same_session():
    lock = LocalTurnLock()
    order = []

    async def worker(n, delay):
        async with lock.hold("sess", owner=f"r{n}", ttl=60.0):
            order.append(("start", n))
            await asyncio.sleep(delay)
            order.append(("end", n))

    async def run():
        await asyncio.gather(worker(1, 0.05), worker(2, 0.0))

    asyncio.run(run())

    # Turns must not interleave: the first started turn ends before the
    # second begins (each ("start", n) is immediately followed by ("end", n)).
    assert order[0][0] == "start"
    first = order[0][1]
    assert order[1] == ("end", first), order


def test_local_turn_lock_allows_concurrent_distinct_sessions():
    lock = LocalTurnLock()
    running = []
    max_concurrent = 0

    async def worker(key):
        nonlocal max_concurrent
        async with lock.hold(key, owner="r", ttl=60.0):
            running.append(key)
            max_concurrent = max(max_concurrent, len(running))
            await asyncio.sleep(0.02)
            running.remove(key)

    async def run():
        await asyncio.gather(worker("a"), worker("b"))

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
