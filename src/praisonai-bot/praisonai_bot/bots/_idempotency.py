"""
Durable inbound webhook/trigger idempotency store for the PraisonAI gateway.

The gateway's inbound HTTP hook surface deduplicates provider redeliveries so a
webhook that re-POSTs an already-processed event does not start a second agent
run (a duplicate reply, or a duplicate tool action). The core in-memory default
(``InMemoryIdempotencyStore``) is per-process and empty after a restart, so this
SQLite-backed store persists the dedup key — mirroring the durability the
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
    backend: str,
    *,
    path: Union[str, Path, None] = None,
    max_size: int = _DEFAULT_MAX_SIZE,
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    inflight_lease_seconds: float = _DEFAULT_INFLIGHT_LEASE_SECONDS,
):
    """Build an idempotency store for the given ``backend``.

    ``"memory"`` (default) returns the core in-memory store; ``"sqlite"``
    returns the durable :class:`SqliteIdempotencyStore`. On any failure to build
    the durable store, falls back to the in-memory default so inbound delivery
    keeps working (dedup is best-effort within the process, as before).
    """
    from praisonaiagents.gateway import InMemoryIdempotencyStore

    def _memory():
        return InMemoryIdempotencyStore(
            max_entries=max_size, ttl_seconds=ttl_seconds
        )

    backend = (backend or "memory").lower()
    if backend == "memory":
        return _memory()
    if backend == "sqlite":
        try:
            store_path = path or (
                Path.home() / ".praisonai" / "state" / "hook_idempotency.sqlite"
            )
            return SqliteIdempotencyStore(
                store_path,
                max_size=max_size,
                ttl_seconds=ttl_seconds,
                inflight_lease_seconds=inflight_lease_seconds,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "SqliteIdempotencyStore unavailable, falling back to in-memory "
                "inbound dedup: %s",
                e,
            )
            return _memory()
    # "redis" (multi-replica) is not yet implemented in the wrapper; fall back
    # to the durable SQLite store if a path is available, else in-memory.
    logger.debug(
        "Idempotency store_backend %r not available; using in-memory default",
        backend,
    )
    return _memory()
