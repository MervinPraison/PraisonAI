"""Distributed per-turn lock for the gateway (Issue #4655).

The gateway's per-turn serialisation seam (``BotSessionManager._locks``) consumes
a ``LockMap``-shaped object: ``.get(key)`` returns something usable in
``async with`` that serialises turns for that key. The default in-process
``LockMap`` only serialises *within one process*, so a horizontally-scaled
gateway (``replicas > 1``) still runs concurrent turns against one resolved
session — the failure ``gateway.turn_lock.backend="redis"`` promises to prevent.

``RedisTurnLock`` is a drop-in, ``LockMap``-compatible replacement that acquires
a cluster-wide lease per resolved-session key using the scheduler's proven
owner+TTL lease pattern (``SET NX PX`` to claim, compare-and-del to release), so
a crashed holder's lease auto-expires after ``ttl`` and can never wedge a healthy
session. On any Redis outage it **fails open** (degrades to a local
``asyncio.Lock`` and records a ``DegradedCapabilityRegistry`` entry) rather than
wedging a live session — mirroring the fail-safe defaults elsewhere in the
gateway.

The heavy Redis dependency and connection lifecycle live here in the wrapper/bot
package; core only owns the protocol and config (``TurnLockProtocol`` /
``TurnLockConfig``), keeping the protocol-driven core dependency-free.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ``owner_kind`` must be one of the core ``OWNER_KINDS`` (capability fits a
# gateway-internal serialisation control); ``owner_id`` names the mechanism.
_DEGRADED_OWNER_KIND = "capability"
_DEGRADED_OWNER_ID = "turn_lock:redis"


class _RedisLease:
    """Async context manager holding one distributed lease for a key.

    Claims ``key`` with ``SET NX PX`` (owner token + TTL). On acquire failure it
    polls until the current holder's lease is free or expires. On a Redis outage
    it falls back to the local lock so a live turn is never wedged (fail-open).
    Release is a compare-and-del on the owner token: an expired/reclaimed lease
    is a harmless no-op, never another replica's lease.
    """

    def __init__(self, lock: "RedisTurnLock", key: str) -> None:
        self._lock = lock
        self._redis_key = lock._redis_key(key)
        self._local_key = key
        self._token = uuid.uuid4().hex
        self._local_lock: Optional[asyncio.Lock] = None
        self._have_remote = False
        self._renew_task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> "_RedisLease":
        # Always hold the in-process lock too: it serialises same-process
        # waiters cheaply and is the fail-open fallback when Redis is down.
        self._local_lock = self._lock._local.get(self._local_key)
        await self._local_lock.acquire()
        # Any failure or cancellation after this point (e.g. BotOS.stop cancels
        # in-flight bot tasks during the drain window) must release the local
        # lock — otherwise the held asyncio.Lock is never evicted and every later
        # turn for this session blocks forever in-process.
        try:
            ttl_ms = max(1, int(self._lock._ttl * 1000))
            poll = self._lock._poll_interval
            while True:
                try:
                    ok = await self._lock._client.set(
                        self._redis_key, self._token, nx=True, px=ttl_ms
                    )
                except Exception as e:  # Redis outage -> fail open on local lock.
                    self._lock._mark_degraded(str(e))
                    self._have_remote = False
                    return self
                if ok:
                    self._lock._clear_degraded()
                    self._have_remote = True
                    # Renew the lease while the turn runs so a turn longer than
                    # ``ttl`` never lets another replica claim the same session.
                    self._renew_task = asyncio.ensure_future(self._renew_loop())
                    return self
                # Held by another replica; poll until its lease frees or expires
                # (the holder's ``px`` TTL guarantees this loop is bounded).
                await asyncio.sleep(poll)
        except BaseException:
            if self._local_lock.locked():
                self._local_lock.release()
            raise

    async def _renew_loop(self) -> None:
        """Extend our lease at ~ttl/3 so a long turn keeps the session (owner-checked)."""
        interval = max(self._lock._poll_interval, self._lock._ttl / 3.0)
        ttl_ms = max(1, int(self._lock._ttl * 1000))
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._lock._renew_remote(
                        self._redis_key, self._token, ttl_ms
                    )
                except Exception as e:  # pragma: no cover - best-effort renewal
                    logger.debug("Failed to renew redis turn lease: %s", e)
        except asyncio.CancelledError:  # pragma: no cover - normal teardown
            pass

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._renew_task is not None:
                self._renew_task.cancel()
                try:
                    await self._renew_task
                except (asyncio.CancelledError, Exception):  # pragma: no cover
                    pass
            if self._have_remote:
                try:
                    await self._lock._release_remote(self._redis_key, self._token)
                except Exception as e:  # pragma: no cover - best-effort release
                    logger.debug("Failed to release redis turn lease: %s", e)
        finally:
            if self._local_lock is not None and self._local_lock.locked():
                self._local_lock.release()


class RedisTurnLock:
    """Distributed, ``LockMap``-compatible per-turn lock (Issue #4655).

    Exposes the same ``.get(key)`` / ``.drop(key)`` / ``.size()`` surface as
    :class:`~praisonai_bot._lockmap.LockMap` so it drops into the existing
    ``BotSessionManager._locks`` seam with no session-layer change. Each
    ``.get(key)`` returns an async context manager that holds a cluster-wide
    lease for the resolved-session key while a turn runs.
    """

    # Lua: delete only if the value still equals our owner token (atomic
    # compare-and-del), so we never release a lease another replica reclaimed.
    _RELEASE_LUA = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )

    # Lua: extend the TTL only if the value still equals our owner token, so a
    # lease another replica reclaimed after expiry is never extended.
    _RENEW_LUA = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end"
    )

    def __init__(
        self,
        client: Any,
        *,
        ttl: float = 60.0,
        prefix: str = "praison:turnlock:",
        poll_interval: float = 0.05,
        degraded_registry: Optional[Any] = None,
    ) -> None:
        from .._lockmap import LockMap

        self._client = client
        self._ttl = float(ttl)
        self._prefix = prefix
        self._poll_interval = poll_interval
        self._local = LockMap()
        self._degraded_registry = degraded_registry
        self._degraded = False

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> _RedisLease:
        """Return an async context manager holding the lease for ``key``."""
        return _RedisLease(self, str(key))

    def drop(self, key: str) -> None:
        """Best-effort local cleanup; the remote lease expires via TTL."""
        try:
            self._local.drop(str(key))
        except Exception:  # pragma: no cover - defensive
            pass

    def size(self) -> int:
        return self._local.size()

    async def _release_remote(self, redis_key: str, token: str) -> None:
        try:
            await self._client.eval(self._RELEASE_LUA, 1, redis_key, token)
        except Exception:
            # Fallback for clients without eval: best-effort compare-and-del.
            current = await self._client.get(redis_key)
            if current == token:
                await self._client.delete(redis_key)

    async def _renew_remote(self, redis_key: str, token: str, ttl_ms: int) -> None:
        """Owner-checked lease extension (compare-and-PEXPIRE)."""
        try:
            await self._client.eval(self._RENEW_LUA, 1, redis_key, token, ttl_ms)
        except Exception:
            # Fallback for clients without eval: renew only if still ours.
            current = await self._client.get(redis_key)
            if current == token:
                # Re-claim (SET without NX) preserving the owner token + TTL.
                await self._client.set(redis_key, token, px=ttl_ms)

    def _mark_degraded(self, reason: str) -> None:
        """Record a degraded turn-lock capability (Issue #4655 fail-open)."""
        already = self._degraded
        self._degraded = True
        if not already:
            logger.warning(
                "Distributed turn lock degraded to local-only "
                "(Redis unavailable): %s", reason
            )
        registry = self._degraded_registry
        if registry is None:
            return
        try:
            from praisonaiagents.gateway.degraded_state import DegradedOwner

            registry.mark(
                DegradedOwner(
                    owner_kind=_DEGRADED_OWNER_KIND,
                    owner_id=_DEGRADED_OWNER_ID,
                    state="stale",
                    reason=f"distributed turn lock unavailable: {reason}",
                    retry_hint=(
                        "check Redis connectivity; turns serialise per-process "
                        "only until it recovers; see `praisonai gateway doctor`"
                    ),
                )
            )
        except Exception as e:  # pragma: no cover - registry is best-effort
            logger.debug("Failed to mark turn-lock degraded: %s", e)

    def _clear_degraded(self) -> None:
        if not self._degraded:
            return
        self._degraded = False
        registry = self._degraded_registry
        if registry is None:
            return
        try:
            registry.clear(_DEGRADED_OWNER_KIND, _DEGRADED_OWNER_ID)
        except Exception as e:  # pragma: no cover - registry is best-effort
            logger.debug("Failed to clear turn-lock degraded: %s", e)


def build_turn_lock(
    turn_lock_config: Optional[Any],
    redis_config: Optional[Any] = None,
    *,
    degraded_registry: Optional[Any] = None,
) -> Any:
    """Select the per-turn lock backend from ``TurnLockConfig`` (Issue #4655).

    Returns a ``LockMap``-compatible object. For the default ``"local"`` backend
    (or when no config is given) this is a plain in-process ``LockMap`` — today's
    behaviour, byte-for-byte. For ``"redis"`` it constructs a
    :class:`RedisTurnLock` reusing the gateway's configured ``RedisConfig`` (or
    the ``turn_lock.url`` override), so turns serialise cluster-wide.

    Construction fails *open*: if Redis cannot be reached the caller gets a
    degraded ``RedisTurnLock`` (local fallback + a ``DegradedCapabilityRegistry``
    entry) rather than a silent downgrade — the outage surfaces in
    ``health()`` / ``doctor``.
    """
    from .._lockmap import LockMap

    enabled = bool(getattr(turn_lock_config, "enabled", False))
    if turn_lock_config is None or not enabled:
        return LockMap()

    url = getattr(turn_lock_config, "url", None)
    ttl = float(getattr(turn_lock_config, "ttl", 60.0))

    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning(
            "gateway.turn_lock.backend='redis' selected but redis[asyncio] is "
            "not installed; turns serialise per-process only. "
            "Install with: pip install redis"
        )
        _record_build_failure(degraded_registry, "redis package not installed")
        return LockMap()

    try:
        if url:
            client = aioredis.from_url(url, decode_responses=True)
        elif redis_config is not None and getattr(redis_config, "url", None):
            client = aioredis.from_url(redis_config.url, decode_responses=True)
        elif redis_config is not None:
            client = aioredis.Redis(
                host=getattr(redis_config, "host", "localhost"),
                port=getattr(redis_config, "port", 6379),
                db=getattr(redis_config, "db", 0),
                password=getattr(redis_config, "password", None),
                decode_responses=True,
            )
        else:
            logger.warning(
                "gateway.turn_lock.backend='redis' selected but no Redis URL or "
                "RedisConfig is available; turns serialise per-process only."
            )
            _record_build_failure(degraded_registry, "no Redis connection configured")
            return LockMap()
    except Exception as e:  # pragma: no cover - construction is defensive
        logger.warning("Failed to build distributed turn lock: %s", e)
        _record_build_failure(degraded_registry, str(e))
        return LockMap()

    prefix = getattr(redis_config, "prefix", "praison:") if redis_config else "praison:"
    return RedisTurnLock(
        client,
        ttl=ttl,
        prefix=f"{prefix}turnlock:",
        degraded_registry=degraded_registry,
    )


def _record_build_failure(registry: Optional[Any], reason: str) -> None:
    if registry is None:
        return
    try:
        from praisonaiagents.gateway.degraded_state import DegradedOwner

        registry.mark(
            DegradedOwner(
                owner_kind=_DEGRADED_OWNER_KIND,
                owner_id=_DEGRADED_OWNER_ID,
                state="stale",
                reason=f"distributed turn lock unavailable: {reason}",
                retry_hint=(
                    "turns serialise per-process only; see "
                    "`praisonai gateway doctor`"
                ),
            )
        )
    except Exception as e:  # pragma: no cover - registry is best-effort
        logger.debug("Failed to record turn-lock build failure: %s", e)
