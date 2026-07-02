"""
Shared SQLite store for cross-worker delivery-control state (issue #2579).

The durable delivery stack (outbox, DLQs, ingress journal, approval store) is
already SQLite-first. The *delivery-control* state that decides how fast and
whether to send, however, was per-process: the rate limiter kept its token
bucket in memory and the dead-target registry rewrote a whole JSON file on
every change. Under a horizontally-scaled gateway N workers each keep their own
token bucket, so the global send rate becomes ~N× the platform ceiling — exactly
the 429s the limiter exists to prevent.

This module provides a small SQLite-backed store that both ``RateLimiter`` and
``DeadTargetRegistry`` can share so their state is correct across workers and
survives restart. It follows the same conventions as ``_outbox.py``:

  - stdlib ``sqlite3`` only (no extra dependency);
  - WAL journal + ``BEGIN IMMEDIATE`` for atomic read-modify-write across
    processes;
  - per-instance ``threading.Lock`` to serialise same-process access.

Single-process gateways can keep the fast in-memory / JSON behaviour by simply
not passing a store; the shared store is what makes multi-worker correct.

Storage schema::

    rate_limit_state(
        scope TEXT PRIMARY KEY,   -- limiter identity (platform / bot token hash)
        tokens REAL,
        last_refill REAL,         -- wall-clock (time.time) reservation anchor
        global_penalty_until REAL
    )
    rate_limit_channel(
        scope TEXT,
        channel_id TEXT,
        last_send REAL,           -- wall-clock projected next-send time
        penalty_until REAL,
        PRIMARY KEY(scope, channel_id)
    )
    dead_targets(
        platform TEXT,
        channel_id TEXT,
        reason TEXT,
        ts REAL,
        PRIMARY KEY(platform, channel_id)
    )

Note on the clock: the in-memory limiter uses ``time.monotonic()`` which is
per-process and cannot be shared. The shared store therefore uses
``time.time()`` (wall clock) for its reservation anchors so multiple processes
agree on a common timeline.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class DeliveryControlStore:
    """SQLite-backed shared store for rate-limit and dead-target state.

    Args:
        path: SQLite file path. Created if missing; parent dirs created. Can be
            the same file the outbox/DLQ use, or a dedicated one.
    """

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── Connection / schema ─────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            return conn
        except Exception:
            conn.close()
            raise

    def _init_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_state (
                    scope TEXT PRIMARY KEY,
                    tokens REAL NOT NULL,
                    last_refill REAL NOT NULL,
                    global_penalty_until REAL NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_channel (
                    scope TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    last_send REAL NOT NULL DEFAULT 0,
                    penalty_until REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (scope, channel_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_targets (
                    platform TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    ts REAL NOT NULL,
                    PRIMARY KEY (platform, channel_id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_dead_ts ON dead_targets(ts)"
            )
            conn.commit()

    # ── Rate-limit token reservation (atomic across workers) ────────
    def reserve_tokens(
        self,
        scope: str,
        *,
        now: float,
        burst_size: float,
        messages_per_second: float,
        channel_id: Optional[str],
        per_channel_delay: float,
        channel_cap: int = 4096,
    ) -> float:
        """Atomically reserve one send slot and return the required wait (seconds).

        Mirrors the in-memory token-bucket + per-channel-delay + penalty logic of
        ``RateLimiter.acquire`` but reads and writes the shared row under a single
        ``BEGIN IMMEDIATE`` transaction, so N workers draw from one bucket. The
        caller sleeps for the returned duration OUTSIDE any lock.
        """
        with self._lock, closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT tokens, last_refill, global_penalty_until "
                    "FROM rate_limit_state WHERE scope = ?",
                    (scope,),
                ).fetchone()
                if row is None:
                    tokens = float(burst_size)
                    last_refill = now
                    global_penalty_until = 0.0
                else:
                    tokens, last_refill, global_penalty_until = (
                        float(row[0]), float(row[1]), float(row[2])
                    )

                # Refill based on elapsed wall-clock since last reservation anchor.
                elapsed = now - last_refill
                if elapsed > 0:
                    tokens = min(burst_size, tokens + elapsed * messages_per_second)
                last_refill = now

                global_wait = 0.0
                if tokens < 1.0:
                    global_wait = (1.0 - tokens) / messages_per_second
                    tokens = 1.0
                    last_refill = now + global_wait
                tokens -= 1.0

                if global_penalty_until > now + global_wait:
                    global_wait = global_penalty_until - now
                    last_refill = max(last_refill, now + global_wait)

                conn.execute(
                    "INSERT INTO rate_limit_state(scope, tokens, last_refill, "
                    "global_penalty_until) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(scope) DO UPDATE SET tokens=excluded.tokens, "
                    "last_refill=excluded.last_refill, "
                    "global_penalty_until=excluded.global_penalty_until",
                    (scope, tokens, last_refill, global_penalty_until),
                )

                channel_wait = 0.0
                if channel_id:
                    crow = conn.execute(
                        "SELECT last_send, penalty_until FROM rate_limit_channel "
                        "WHERE scope = ? AND channel_id = ?",
                        (scope, channel_id),
                    ).fetchone()
                    last = float(crow[0]) if crow else 0.0
                    penalty_until = float(crow[1]) if crow else 0.0
                    projected_now = now + global_wait
                    c_elapsed = projected_now - last
                    if c_elapsed < per_channel_delay:
                        channel_wait = per_channel_delay - c_elapsed
                    if penalty_until > projected_now + channel_wait:
                        channel_wait = penalty_until - projected_now
                    elif penalty_until and penalty_until <= now:
                        penalty_until = 0.0
                    conn.execute(
                        "INSERT INTO rate_limit_channel(scope, channel_id, "
                        "last_send, penalty_until) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(scope, channel_id) DO UPDATE SET "
                        "last_send=excluded.last_send, "
                        "penalty_until=excluded.penalty_until",
                        (scope, channel_id, projected_now + channel_wait, penalty_until),
                    )
                    self._enforce_channel_bound(conn, scope, channel_cap)

                conn.commit()
                return global_wait + channel_wait
            except Exception:
                conn.rollback()
                raise

    def penalise(
        self,
        scope: str,
        channel_id: Optional[str],
        *,
        until: float,
    ) -> None:
        """Widen a lane by recording a hold-off window (server 429/Retry-After)."""
        with self._lock, closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if channel_id:
                    crow = conn.execute(
                        "SELECT penalty_until FROM rate_limit_channel "
                        "WHERE scope = ? AND channel_id = ?",
                        (scope, channel_id),
                    ).fetchone()
                    cur = float(crow[0]) if crow else 0.0
                    conn.execute(
                        "INSERT INTO rate_limit_channel(scope, channel_id, "
                        "last_send, penalty_until) VALUES (?, ?, 0, ?) "
                        "ON CONFLICT(scope, channel_id) DO UPDATE SET "
                        "penalty_until=excluded.penalty_until",
                        (scope, channel_id, max(cur, until)),
                    )
                else:
                    row = conn.execute(
                        "SELECT tokens, last_refill, global_penalty_until "
                        "FROM rate_limit_state WHERE scope = ?",
                        (scope,),
                    ).fetchone()
                    if row is None:
                        conn.execute(
                            "INSERT INTO rate_limit_state(scope, tokens, "
                            "last_refill, global_penalty_until) VALUES (?, 0, ?, ?)",
                            (scope, time.time(), until),
                        )
                    else:
                        cur = float(row[2])
                        conn.execute(
                            "UPDATE rate_limit_state SET global_penalty_until = ? "
                            "WHERE scope = ?",
                            (max(cur, until), scope),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def reset_rate_limit(self, scope: str) -> None:
        """Clear all shared rate-limit state for a scope."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM rate_limit_state WHERE scope = ?", (scope,))
            conn.execute("DELETE FROM rate_limit_channel WHERE scope = ?", (scope,))
            conn.commit()

    @staticmethod
    def _enforce_channel_bound(
        conn: sqlite3.Connection, scope: str, cap: int
    ) -> None:
        if cap <= 0:
            return
        n = conn.execute(
            "SELECT COUNT(*) FROM rate_limit_channel WHERE scope = ?", (scope,)
        ).fetchone()[0]
        if n <= cap:
            return
        conn.execute(
            "DELETE FROM rate_limit_channel WHERE rowid IN ("
            "SELECT rowid FROM rate_limit_channel WHERE scope = ? "
            "ORDER BY last_send ASC LIMIT ?)",
            (scope, n - cap),
        )

    # ── Dead-target registry (atomic row upsert) ────────────────────
    def dead_mark(self, platform: str, channel_id: str, reason: str) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO dead_targets(platform, channel_id, reason, ts) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(platform, channel_id) DO UPDATE SET "
                "reason=excluded.reason, ts=excluded.ts",
                (platform, channel_id, reason, time.time()),
            )
            conn.commit()

    def dead_clear(self, platform: str, channel_id: str) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM dead_targets WHERE platform = ? AND channel_id = ?",
                (platform, channel_id),
            )
            conn.commit()

    def dead_get_ts(self, platform: str, channel_id: str) -> Optional[float]:
        with self._lock, closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT ts FROM dead_targets WHERE platform = ? AND channel_id = ?",
                (platform, channel_id),
            ).fetchone()
            return float(row[0]) if row else None

    def dead_expire(self, cutoff: float) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM dead_targets WHERE ts < ?", (cutoff,))
            conn.commit()

    def dead_enforce_bound(self, max_size: int) -> None:
        if max_size <= 0:
            return
        with self._lock, closing(self._connect()) as conn:
            n = conn.execute("SELECT COUNT(*) FROM dead_targets").fetchone()[0]
            if n <= max_size:
                return
            conn.execute(
                "DELETE FROM dead_targets WHERE rowid IN ("
                "SELECT rowid FROM dead_targets ORDER BY ts ASC LIMIT ?)",
                (n - max_size,),
            )
            conn.commit()

    def dead_list(self) -> List[Tuple[str, str, str, float]]:
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT platform, channel_id, reason, ts FROM dead_targets "
                "ORDER BY ts ASC"
            ).fetchall()
            return [(str(r[0]), str(r[1]), str(r[2]), float(r[3])) for r in rows]

    def dead_count(self) -> int:
        with self._lock, closing(self._connect()) as conn:
            return int(
                conn.execute("SELECT COUNT(*) FROM dead_targets").fetchone()[0]
            )


__all__ = ["DeliveryControlStore"]
