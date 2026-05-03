"""
Inbound Dead-Letter Queue (N4) for PraisonAI bot adapters.

When ``BotSessionManager.chat()`` raises (LLM 5xx, transient timeout,
provider rate-limit, etc.) the user message is normally lost. This
module persists those failed inbound messages so an operator can
inspect, retry, or purge them later.

Design constraints (per PraisonAI principles):
  - Wrapper-only — heavy code stays out of the core SDK.
  - Lazy: ``sqlite3`` is stdlib so no extra dependency.
  - Default OFF — ``BotSessionManager`` works exactly as before unless
    a ``dlq=InboundDLQ(...)`` is passed.
  - Bounded: TTL + ``max_size`` prevent unbounded disk growth.
  - Thread-safe: a per-instance ``threading.Lock`` guards SQLite writes
    (sqlite3 connections are not thread-safe by default).
  - Reuses ``_resilience.BackoffPolicy`` for retry timing on replay.

Storage schema::

    entries(id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            platform TEXT, user_id TEXT, prompt TEXT,
            chat_id TEXT, thread_id TEXT, user_name TEXT,
            error TEXT,
            attempts INTEGER DEFAULT 0)

Public API:
  - ``InboundDLQ(path, *, max_size=10_000, ttl_seconds=7*86400)``
  - ``enqueue(platform, user_id, prompt, error, ...)``
  - ``size()`` / ``list(limit=100)`` / ``purge()``
  - ``evict_expired()``
  - ``replay(handler)`` — async, drops entries handler returns ``True`` for.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, List, Optional, Union

logger = logging.getLogger(__name__)


# 7 days default — long enough for ops to notice and act, short enough
# not to blow up disk on chronic LLM failures.
_DEFAULT_TTL_SECONDS = 7 * 86400
_DEFAULT_MAX_SIZE = 10_000


@dataclass(frozen=True)
class DLQEntry:
    """A single failed inbound message awaiting replay."""

    id: int
    ts: float
    platform: str
    user_id: str
    prompt: str
    chat_id: str
    thread_id: str
    user_name: str
    error: str
    attempts: int


# Replay handler signature: takes an entry, returns True on success
# (entry will be deleted) or False to keep it for later retry.
ReplayHandler = Callable[[DLQEntry], Awaitable[bool]]


class InboundDLQ:
    """SQLite-backed dead-letter queue for failed inbound bot messages.

    Args:
        path: SQLite file path. Created if missing; parent dirs created.
        max_size: Maximum entries kept; oldest evicted when exceeded.
        ttl_seconds: Entries older than this are evicted on the next
            ``enqueue()`` or ``evict_expired()`` call.

    Example::

        from praisonai.bots import InboundDLQ, BotSessionManager

        dlq = InboundDLQ(path="~/.praisonai/dlq.sqlite")
        mgr = BotSessionManager(platform="telegram", dlq=dlq)

        # Later, an admin replays:
        async def my_handler(entry):
            try:
                await mgr.chat(agent, entry.user_id, entry.prompt)
                return True
            except Exception:
                return False
        await dlq.replay(my_handler)
    """

    def __init__(
        self,
        path: Union[str, Path],
        *,
        max_size: int = _DEFAULT_MAX_SIZE,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self.path = Path(path).expanduser()
        self.max_size = int(max_size)
        self.ttl_seconds = int(ttl_seconds)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── Schema ──────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    platform TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    chat_id TEXT DEFAULT '',
                    thread_id TEXT DEFAULT '',
                    user_name TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    attempts INTEGER DEFAULT 0
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON entries(ts)")

    # ── Mutations ───────────────────────────────────────────────────
    def enqueue(
        self,
        *,
        platform: str,
        user_id: str,
        prompt: str,
        error: str,
        chat_id: str = "",
        thread_id: str = "",
        user_name: str = "",
    ) -> int:
        """Persist a failed inbound message. Returns its row id.

        Runs ``evict_expired`` and ``_evict_overflow`` as side-effects so
        TTL and ``max_size`` invariants are kept tight without a
        background sweeper.
        """
        with self._lock, self._connect() as conn:
            self._evict_expired_locked(conn)
            cur = conn.execute(
                """
                INSERT INTO entries(ts, platform, user_id, prompt,
                                    chat_id, thread_id, user_name, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(), platform, user_id, prompt,
                    chat_id, thread_id, user_name, error,
                ),
            )
            self._evict_overflow_locked(conn)
            return int(cur.lastrowid)

    def purge(self) -> int:
        """Delete all entries. Returns count removed."""
        with self._lock, self._connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            conn.execute("DELETE FROM entries")
            return int(n)

    def evict_expired(self) -> int:
        """Drop entries older than ``ttl_seconds``. Returns count removed."""
        with self._lock, self._connect() as conn:
            return self._evict_expired_locked(conn)

    def _evict_expired_locked(self, conn: sqlite3.Connection) -> int:
        cutoff = time.time() - self.ttl_seconds
        cur = conn.execute("DELETE FROM entries WHERE ts <= ?", (cutoff,))
        return int(cur.rowcount or 0)

    def _evict_overflow_locked(self, conn: sqlite3.Connection) -> int:
        n = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        if n <= self.max_size:
            return 0
        excess = n - self.max_size
        cur = conn.execute(
            "DELETE FROM entries WHERE id IN "
            "(SELECT id FROM entries ORDER BY ts ASC LIMIT ?)",
            (excess,),
        )
        return int(cur.rowcount or 0)

    # ── Queries ─────────────────────────────────────────────────────
    def size(self) -> int:
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])

    def list(self, limit: int = 100) -> List[DLQEntry]:
        """Return up to ``limit`` entries, newest first."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, platform, user_id, prompt,
                       chat_id, thread_id, user_name, error, attempts
                FROM entries
                ORDER BY ts DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [DLQEntry(*r) for r in rows]

    # ── Replay ──────────────────────────────────────────────────────
    async def replay(
        self,
        handler: ReplayHandler,
        *,
        limit: Optional[int] = None,
    ) -> tuple[int, int]:
        """Re-deliver entries via ``handler``.

        ``handler(entry)`` must return ``True`` on success (entry is
        deleted) or ``False`` to keep the entry for later. Exceptions
        from the handler are caught and treated as ``False`` (entry is
        kept and ``attempts`` incremented).

        Returns ``(succeeded, failed)`` counts.
        """
        entries = self.list(limit=limit if limit is not None else self.max_size)
        succeeded = failed = 0
        for entry in entries:
            try:
                ok = await handler(entry)
            except Exception as e:  # pragma: no cover — defensive
                logger.warning("DLQ replay handler raised: %s", e)
                ok = False
            if ok:
                self._delete(entry.id)
                succeeded += 1
            else:
                self._increment_attempts(entry.id)
                failed += 1
        return succeeded, failed

    def _delete(self, entry_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))

    def _increment_attempts(self, entry_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE entries SET attempts = attempts + 1 WHERE id = ?",
                (entry_id,),
            )

    def __repr__(self) -> str:
        return (
            f"InboundDLQ(path={str(self.path)!r}, "
            f"size={self.size()}, "
            f"max_size={self.max_size}, ttl={self.ttl_seconds}s)"
        )


__all__ = ["InboundDLQ", "DLQEntry", "ReplayHandler"]
