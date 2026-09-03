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


def build_idempotency_store(
    backend: Union[str, None] = None,
    *,
    path: Union[str, Path, None] = None,
    max_size: int = _DEFAULT_MAX_SIZE,
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    inflight_lease_seconds: float = _DEFAULT_INFLIGHT_LEASE_SECONDS,
):
    """Build an idempotency store for the given ``backend``.

    Durable by default (Issue #4339): when ``backend`` is unset (``None``) a
    durable :class:`SqliteIdempotencyStore` is chosen so an out-of-box gateway
    survives a restart within a provider's retry window rather than silently
    re-processing a redelivered webhook. ``"memory"`` stays available as an
    **explicit** opt-in for tests / ephemeral runs, and ``"sqlite"`` forces the
    durable store. If the durable store genuinely cannot be initialised, this
    records a *durability-degraded* fact (surfaced by ``gateway doctor`` /
    ``gateway status``) and falls back to in-memory so inbound delivery keeps
    working — degradation is reported, not silent.
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
        # A cross-replica Redis idempotency backend is not yet implemented in
        # the wrapper (unlike ``RedisTurnLock`` for the turn lock). Selecting it
        # must therefore never *silently* downgrade to per-replica dedup — that
        # is the "silent failure > crash" trap (#4768): the operator asked for
        # cross-replica idempotency and would otherwise see a green health
        # surface while duplicate deliveries run the same turn twice. Mirror the
        # SQLite-failure path: record the durability-degraded fact so
        # ``health()`` / ``gateway status`` / ``gateway doctor`` report it, then
        # fall back to the durable SQLite store (still cross-restart dedup, and
        # cross-replica when the state file is shared) rather than in-memory.
        logger.warning(
            "Idempotency store_backend='redis' is not implemented; inbound "
            "dedup runs per-replica (durable SQLite fallback). A message "
            "delivered to multiple replicas that do not share the state file "
            "may be processed more than once. Install a shared state dir or "
            "use a single replica until a Redis backend is available."
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
