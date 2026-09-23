"""
Durable inbound webhook/trigger idempotency store for the PraisonAI gateway.

The gateway's inbound HTTP hook surface deduplicates provider redeliveries so a
webhook that re-POSTs an already-processed event does not start a second agent
run (a duplicate reply, or a duplicate tool action). The core in-memory store
(``InMemoryIdempotencyStore``) is per-process and empty after a restart, so this
SQLite-backed store — selected by default (Issue #4339) — persists the dedup key,
mirroring the durability the
``InboundJournal`` and ``OutboundQueue`` already provide — so the dedup window
survives a restart within a provider's retry window and, when the same DB file
is shared, across replicas.

Design constraints (per PraisonAI principles):
  - Wrapper-only — heavy implementation stays out of core SDK
  - Lazy: sqlite3 is stdlib so no extra dependency
  - Optional: the gateway uses the in-memory default unless this is configured
  - Bounded: TTL + max_size prevent unbounded disk growth
  - Thread-safe: per-instance threading.Lock guards SQLite writes
  - Atomic: reserve is a durable ``UNIQUE`` insert, so "already seen or in
    flight" is a single crash-safe claim (an inbound analogue of the outbound
    queue's ``UNIQUE idempotency_key``)

Storage schema::

    hook_idempotency(
        key TEXT PRIMARY KEY,
        ts REAL,          -- reservation/record time (seconds)
        status TEXT       -- 'inflight' | 'recorded'
    )

Public API mirrors ``IdempotencyStoreProtocol``:
  - reserve(key) -> bool   # False if seen-or-in-flight (durable)
  - record(key) -> None    # commit after a successful run
  - release(key) -> None   # allow retry after a failed run
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

_DEFAULT_MAX_SIZE = 10_000
_DEFAULT_TTL_SECONDS = 86_400.0  # 24h, matching the in-memory default
# An ``inflight`` reservation whose run neither recorded nor released it — the
# only durable cause is a process crash *during* the hook — is reclaimable after
# this lease. It bounds how long a crashed delivery is (wrongly) deduplicated
# before the provider's retry can re-run it, while staying long enough that a
# genuinely slow in-flight run is never stolen by a concurrent duplicate. Only
# ``inflight`` rows are reclaimed; a ``recorded`` key dedups until its TTL.
_DEFAULT_INFLIGHT_LEASE_SECONDS = 900.0  # 15 min


class SqliteIdempotencyStore:
    """SQLite-backed durable :class:`IdempotencyStoreProtocol`.

    Args:
        path: SQLite file path. Created if missing; parent dirs created.
        max_size: Maximum recorded entries kept; oldest recorded entries evicted
            when exceeded.
        ttl_seconds: Entries older than this are pruned lazily on ``reserve``.
        inflight_lease_seconds: A stale ``inflight`` reservation (crash between
            reserve and record/release) is reclaimable after this lease so the
            provider's retry can re-run rather than being deduplicated for the
            full ``ttl_seconds``.
    """

    def __init__(
        self,
        path: Union[str, Path],
        *,
        max_size: int = _DEFAULT_MAX_SIZE,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        inflight_lease_seconds: float = _DEFAULT_INFLIGHT_LEASE_SECONDS,
    ) -> None:
        self.path = Path(path).expanduser()
        self.max_size = max(1, int(max_size))
        self.ttl_seconds = float(ttl_seconds)
        self.inflight_lease_seconds = float(inflight_lease_seconds)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hook_idempotency(
                    key TEXT PRIMARY KEY,
                    ts REAL NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_hook_idem_ts "
                "ON hook_idempotency(ts)"
            )
            conn.commit()

    def _prune(self, conn: sqlite3.Connection, now: float) -> None:
        conn.execute(
            "DELETE FROM hook_idempotency WHERE ? - ts > ?",
            (now, self.ttl_seconds),
        )
        # Reclaim stale ``inflight`` reservations: a durable ``inflight`` row that
        # outlives the lease can only be a crash between reserve and
        # record/release (a live run records or releases well within the lease).
        # Dropping it lets the provider's post-restart retry re-run instead of
        # being deduplicated for the full TTL. ``recorded`` rows are untouched.
        conn.execute(
            "DELETE FROM hook_idempotency "
            "WHERE status = 'inflight' AND ? - ts > ?",
            (now, self.inflight_lease_seconds),
        )
        # Enforce max size on recorded entries (drop oldest).
        row = conn.execute(
            "SELECT COUNT(*) FROM hook_idempotency WHERE status = 'recorded'"
        ).fetchone()
        count = int(row[0]) if row else 0
        if count > self.max_size:
            excess = count - self.max_size
            conn.execute(
                """
                DELETE FROM hook_idempotency WHERE key IN (
                    SELECT key FROM hook_idempotency
                    WHERE status = 'recorded'
                    ORDER BY ts ASC LIMIT ?
                )
                """,
                (excess,),
            )

    def reserve(self, key: str) -> bool:
        """Atomically claim ``key`` via a durable ``UNIQUE`` insert.

        Returns ``False`` when the key was already recorded *or* is currently in
        flight — the insert fails on the primary-key constraint, so both a
        redelivery and a concurrent duplicate are rejected crash-safely. A
        ``inflight`` reservation orphaned by a crash is first reclaimed by
        :meth:`_prune` once it outlives ``inflight_lease_seconds``, so the insert
        can then succeed and the provider's retry re-runs.
        """
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            self._prune(conn, now)
            try:
                conn.execute(
                    "INSERT INTO hook_idempotency(key, ts, status) "
                    "VALUES (?, ?, 'inflight')",
                    (key, now),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def record(self, key: str) -> None:
        """Commit ``key`` as processed after a successful run."""
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO hook_idempotency(key, ts, status) "
                "VALUES (?, ?, 'recorded') "
                "ON CONFLICT(key) DO UPDATE SET ts = excluded.ts, "
                "status = 'recorded'",
                (key, now),
            )
            conn.commit()

    def release(self, key: str) -> None:
        """Drop an in-flight reservation so a failed delivery can be retried."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM hook_idempotency WHERE key = ? AND status = 'inflight'",
                (key,),
            )
            conn.commit()


class RedisIdempotencyStore:
    """Cluster-wide inbound-dedup :class:`IdempotencyStoreProtocol` (Issue #5154).

    The SQLite store only dedups across replicas when every replica shares one
    state file; without a shared volume the *same* webhook fanned to two
    replicas is admitted on each and processed twice. This store keeps the
    exactly-once claim in Redis so admission is cluster-wide by construction,
    keyed on the deterministic idempotency key ``(platform, account,
    channel_id, message_id)``.

    It reuses the proven ``RedisTurnLock`` lease shape: ``reserve`` is a single
    ``SET NX PX`` (atomic claim + owner token + TTL), so both a redelivery and a
    concurrent duplicate on another replica are rejected crash-safely; a claim
    orphaned by a crash between ``reserve`` and ``record``/``release`` expires
    after ``inflight_lease_seconds`` and the provider's retry re-runs — the same
    self-healing the SQLite store gets from its inflight lease, here for free via
    the key TTL. ``record`` upgrades the claim to a long-lived ``recorded`` value
    (TTL ``ttl_seconds``); ``release`` drops the claim only if we still own it
    (compare-and-del), so a reclaimed lease is never deleted out from under a
    replica that took over.

    The heavy Redis client lives in the wrapper (as with ``RedisTurnLock``);
    core owns only the protocol. This store is *synchronous* to match the
    synchronous :class:`IdempotencyStoreProtocol` seam (the gateway's
    ``_hook_reserve``/``_hook_record``/``_hook_release`` are sync), so it takes a
    synchronous ``redis.Redis`` client, not the async one the turn lock uses.
    """

    _RECORDED = "recorded"

    # Lua: delete only if the stored value still equals our token, so we never
    # release a claim another replica reclaimed after our lease expired.
    _RELEASE_LUA = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )

    def __init__(
        self,
        client,
        *,
        prefix: str = "praison:hookidem:",
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        inflight_lease_seconds: float = _DEFAULT_INFLIGHT_LEASE_SECONDS,
    ) -> None:
        import uuid

        self._client = client
        self._prefix = prefix
        self._ttl_ms = max(1, int(float(ttl_seconds) * 1000))
        self._inflight_ms = max(1, int(float(inflight_lease_seconds) * 1000))
        # A per-instance owner token distinguishes *our* in-flight claim from a
        # ``recorded`` value and from another replica's claim, so ``release`` is
        # a safe compare-and-del.
        self._token = uuid.uuid4().hex

    def _redis_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def reserve(self, key: str) -> bool:
        """Atomically claim ``key`` cluster-wide via ``SET NX PX``.

        Returns ``False`` when the key is already recorded *or* currently claimed
        by any replica — the ``NX`` insert fails, rejecting both a redelivery and
        a concurrent duplicate. A claim orphaned by a crash expires after the
        inflight lease, after which a retry's ``reserve`` succeeds again.
        """
        return bool(
            self._client.set(
                self._redis_key(key), self._token, nx=True, px=self._inflight_ms
            )
        )

    def record(self, key: str) -> None:
        """Commit ``key`` as processed (long-lived ``recorded`` value, TTL)."""
        self._client.set(self._redis_key(key), self._RECORDED, px=self._ttl_ms)

    def release(self, key: str) -> None:
        """Drop our in-flight claim so a failed delivery can be retried.

        Compare-and-del on our owner token: a ``recorded`` value or a claim a
        replica reclaimed after our lease expired is a harmless no-op, never
        another replica's live claim.
        """
        redis_key = self._redis_key(key)
        try:
            self._client.eval(self._RELEASE_LUA, 1, redis_key, self._token)
        except Exception:
            # Fallback for clients without ``eval``: best-effort compare-and-del.
            if self._client.get(redis_key) == self._token:
                self._client.delete(redis_key)


def _build_redis_client(redis_config, url):
    """Construct a synchronous ``redis.Redis`` client, or ``None`` on failure.

    Mirrors ``build_turn_lock``'s client construction but for the *sync* client
    (the idempotency seam is synchronous). Any missing dependency or connection
    failure returns ``None`` so the caller can fail open to the durable SQLite
    store rather than wedging inbound delivery.
    """
    try:
        import redis
    except ImportError:
        logger.warning(
            "Idempotency store_backend='redis' selected but the redis package "
            "is not installed; falling back to durable SQLite. "
            "Install with: pip install redis"
        )
        return None
    try:
        if url:
            client = redis.from_url(url, decode_responses=True)
        elif redis_config is not None and getattr(redis_config, "url", None):
            client = redis.from_url(redis_config.url, decode_responses=True)
        elif redis_config is not None:
            client = redis.Redis(
                host=getattr(redis_config, "host", "localhost"),
                port=getattr(redis_config, "port", 6379),
                db=getattr(redis_config, "db", 0),
                password=getattr(redis_config, "password", None),
                decode_responses=True,
            )
        else:
            logger.warning(
                "Idempotency store_backend='redis' selected but no Redis URL or "
                "RedisConfig is available; falling back to durable SQLite."
            )
            return None
        # Verify connectivity up front so an unreachable Redis fails open at
        # build time (surfaced as a degraded fact) rather than on first reserve.
        client.ping()
        return client
    except Exception as e:  # pragma: no cover - construction is defensive
        logger.warning(
            "Failed to build Redis idempotency store, falling back to durable "
            "SQLite: %s",
            e,
        )
        return None


def build_idempotency_store(
    backend: Union[str, None] = None,
    *,
    path: Union[str, Path, None] = None,
    max_size: int = _DEFAULT_MAX_SIZE,
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    inflight_lease_seconds: float = _DEFAULT_INFLIGHT_LEASE_SECONDS,
    redis_config=None,
    redis_url: Union[str, None] = None,
):
    """Build an idempotency store for the given ``backend``.

    Durable by default (Issue #4339): when ``backend`` is unset (``None``) a
    durable :class:`SqliteIdempotencyStore` is chosen so an out-of-box gateway
    survives a restart within a provider's retry window rather than silently
    re-processing a redelivered webhook. ``"memory"`` stays available as an
    **explicit** opt-in for tests / ephemeral runs, and ``"sqlite"`` forces the
    durable store. ``"redis"`` selects the cluster-wide
    :class:`RedisIdempotencyStore` (Issue #5154) so a webhook fanned to multiple
    replicas is admitted exactly once, reusing the gateway's ``RedisConfig`` (or
    the ``redis_url`` override) exactly as ``build_turn_lock`` does. If the
    durable store genuinely cannot be initialised — or, for ``"redis"``, if
    Redis is unreachable — this records a *durability-degraded* fact (surfaced
    by ``gateway doctor`` / ``gateway status``) and falls back (Redis→durable
    SQLite→in-memory) so inbound delivery keeps working — degradation is
    reported, not silent.
    """
    from praisonaiagents.gateway import InMemoryIdempotencyStore

    def _memory():
        return InMemoryIdempotencyStore(
            max_entries=max_size, ttl_seconds=ttl_seconds
        )

    def _default_path() -> Path:
        return Path.home() / ".praisonai" / "state" / "hook_idempotency.sqlite"

    def _sqlite():
        """Build the durable SQLite store, returning ``(store, durable)``.

        ``durable`` is ``True`` when the SQLite store came up, ``False`` when it
        could not be initialised and this fell back to the in-memory store (and
        recorded the more severe ``running in-memory`` degraded fact). Callers
        that layer their own degraded fact (e.g. the redis fallback) must not
        overwrite that in-memory fact when ``durable`` is ``False``.
        """
        try:
            store_path = Path(path) if path else _default_path()
            store = SqliteIdempotencyStore(
                store_path,
                max_size=max_size,
                ttl_seconds=ttl_seconds,
                inflight_lease_seconds=inflight_lease_seconds,
            )
            # The durable store came up (fresh start, or a recovery after a
            # prior failure/hot-reload): clear any stale degraded fact so a
            # recovered gateway stops reporting non-durable idempotency (#4339).
            from ._session import clear_durability_degraded

            clear_durability_degraded("idempotency")
            return store, True
        except Exception as e:
            # Keep the raw exception (which may embed a filesystem path) in the
            # log only; the operator-facing reason stays redacted so health()
            # and ``gateway status`` never echo backend paths (#4339).
            logger.warning(
                "SqliteIdempotencyStore unavailable, falling back to in-memory "
                "inbound dedup: %s",
                e,
            )
            from ._session import record_durability_degraded

            record_durability_degraded(
                "idempotency",
                reason="durable idempotency store unavailable (running in-memory)",
            )
            return _memory(), False

    # ``None`` means "no explicit choice" → durable by default. ``"memory"``
    # must be asked for; only then do we run non-durably by intent.
    if backend is None:
        backend = "sqlite"
    backend = (backend or "memory").lower()
    if backend == "memory":
        return _memory()
    if backend == "sqlite":
        store, _durable = _sqlite()
        return store
    if backend == "redis":
        # Cross-replica exactly-once admission (Issue #5154). Try the real
        # cluster-wide store first; only if Redis is unreachable / the package
        # is missing do we fall back — and never *silently*: the operator asked
        # for cross-replica dedup and would otherwise see a green health surface
        # while duplicate deliveries run the same turn twice (the "silent
        # failure > crash" trap, #4768). So on fallback we mirror the
        # SQLite-failure path and record the degraded fact.
        client = _build_redis_client(redis_config, redis_url)
        if client is not None:
            prefix = (
                getattr(redis_config, "prefix", "praison:")
                if redis_config is not None
                else "praison:"
            )
            store = RedisIdempotencyStore(
                client,
                prefix=f"{prefix}hookidem:",
                ttl_seconds=ttl_seconds,
                inflight_lease_seconds=inflight_lease_seconds,
            )
            # Cross-replica dedup is now active: clear any prior idempotency
            # degradation so a recovered gateway stops reporting a downgrade.
            from ._session import clear_durability_degraded

            clear_durability_degraded("idempotency")
            return store
        logger.warning(
            "Idempotency store_backend='redis' selected but Redis is "
            "unavailable; inbound dedup falls back per-replica (durable SQLite). "
            "A message delivered to multiple replicas that do not share the "
            "state file may be processed more than once until Redis recovers."
        )
        # Build the SQLite fallback first: its success path clears any prior
        # idempotency degradation, so we must record the redis-unavailable fact
        # *after* it, or the just-recorded fact would be cleared immediately.
        store, durable = _sqlite()
        if durable:
            # SQLite came up: dedup is durable (cross-restart, and cross-replica
            # with a shared state file) but still not the requested cross-replica
            # Redis backend — record the per-replica downgrade.
            from ._session import record_durability_degraded

            record_durability_degraded(
                "idempotency",
                reason="redis idempotency backend not available (running per-replica)",
            )
        # If SQLite *also* failed, ``_sqlite()`` already recorded the more severe
        # "running in-memory" fact (dedup is process-local and lost on restart).
        # Do NOT overwrite it with the milder "per-replica" reason, which would
        # mask the loss of restart durability from health / gateway status (#4768).
        return store
    logger.debug(
        "Idempotency store_backend %r not available; using in-memory default",
        backend,
    )
    return _memory()
