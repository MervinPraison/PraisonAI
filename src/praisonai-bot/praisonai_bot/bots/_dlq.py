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
from typing import Any, Awaitable, Callable, List, Optional, Union

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

        from praisonai_bot.bots import InboundDLQ, BotSessionManager

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
        conn = sqlite3.connect(str(self.path))
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
            try:
                conn.execute("BEGIN IMMEDIATE")
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
                conn.commit()
                return int(cur.lastrowid)
            except Exception:
                conn.rollback()
                raise

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

    def _list_oldest_first(self, limit: int = 100) -> List[DLQEntry]:
        """Return up to ``limit`` entries, oldest first for replay."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, platform, user_id, prompt,
                       chat_id, thread_id, user_name, error, attempts
                FROM entries
                ORDER BY ts ASC
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
        # Fetch entries oldest-first for correct replay order
        entries = self._list_oldest_first(limit=limit if limit is not None else self.max_size)
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


@dataclass(frozen=True)
class OutboundDLQEntry:
    """A single failed outbound message awaiting replay."""

    id: int
    ts: float
    platform: str
    channel_id: str
    reply_text: str
    thread_id: str
    reply_to: str
    error: str
    attempts: int


class OutboundDLQ:
    """SQLite-backed dead-letter queue for failed outbound bot messages.

    When a bot fails to send a response after exhausting retries (due to
    platform errors, rate limits, etc.), this queue preserves the message
    for later replay. This ensures expensive LLM work is never wasted.

    Args:
        path: SQLite file path. Created if missing; parent dirs created.
        max_size: Maximum entries kept; oldest evicted when exceeded.
        ttl_seconds: Entries older than this are evicted on the next
            ``enqueue_outbound()`` or ``evict_expired()`` call.

    Example::

        from praisonai_bot.bots import OutboundDLQ

        dlq = OutboundDLQ(path="~/.praisonai/outbound_dlq.sqlite")

        # In bot adapter, after retries exhausted:
        await dlq.enqueue_outbound(
            platform="telegram",
            channel_id=chat_id,
            reply_text=response,
            error="HTTP 503: Service Unavailable"
        )

        # Later, an admin replays:
        async def replay_handler(entry):
            try:
                await bot.send_message(entry.channel_id, entry.reply_text)
                return True
            except Exception:
                return False
        await dlq.replay(replay_handler)
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
        # Nested-park guard (Issue #3862). While a boot-time drainer redelivers
        # a parked reply through the adapter's normal ``send_message``, a
        # re-failure re-enters ``enqueue_outbound`` via the resilience wrapper
        # and would create a *duplicate* row for the very reply ``replay`` is
        # already keeping + re-attempting. We suppress **only that** nested
        # re-park by matching the in-flight entry's identity — a *different*
        # (genuinely new) reply that fails concurrently is still persisted, so
        # the durable-outbound contract holds even during recovery.
        self._redelivering: Optional[tuple[str, str, str, str]] = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @staticmethod
    def _park_signature(
        platform: str, channel_id: str, reply_text: str, thread_id: str, reply_to: str,
    ) -> tuple[str, str, str, str]:
        # error/ts are intentionally excluded: the same obligation re-parks with
        # a fresh error string and time on each failed redelivery attempt.
        return (platform, channel_id, reply_text, f"{thread_id}\x00{reply_to}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS outbound_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    platform TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    reply_text TEXT NOT NULL,
                    thread_id TEXT DEFAULT '',
                    reply_to TEXT DEFAULT '',
                    error TEXT DEFAULT '',
                    attempts INTEGER DEFAULT 0
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_outbound_ts ON outbound_entries(ts)")

    async def enqueue_outbound(
        self,
        *,
        platform: str,
        channel_id: str,
        reply_text: str,
        error: str,
        thread_id: str = "",
        reply_to: str = "",
    ) -> int:
        """Persist a failed outbound message. Returns its row id.

        Returns ``-1`` without inserting **only** when this call is the nested
        re-park of the exact reply a boot-time drainer is currently
        redelivering (Issue #3862) — that reply's original row is already kept +
        re-attempted by :meth:`redeliver`, so a second row would duplicate it.
        Any other failed reply (a genuinely new obligation) is always persisted,
        even concurrently with a drain, preserving the durable-outbound
        contract.
        """
        if self._redelivering is not None and self._redelivering == self._park_signature(
            platform, channel_id, reply_text, thread_id, reply_to
        ):
            return -1
        # Run synchronous SQLite operations in thread pool to avoid blocking
        import asyncio
        return await asyncio.to_thread(
            self._enqueue_outbound_sync,
            platform=platform,
            channel_id=channel_id,
            reply_text=reply_text,
            error=error,
            thread_id=thread_id,
            reply_to=reply_to,
        )

    def _enqueue_outbound_sync(
        self,
        *,
        platform: str,
        channel_id: str,
        reply_text: str,
        error: str,
        thread_id: str = "",
        reply_to: str = "",
    ) -> int:
        """Synchronous version of enqueue_outbound for thread pool execution."""
        with self._lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._evict_expired_locked(conn)
                cur = conn.execute(
                    """
                    INSERT INTO outbound_entries(ts, platform, channel_id, reply_text,
                                                 thread_id, reply_to, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        time.time(), platform, channel_id, reply_text,
                        thread_id, reply_to, error,
                    ),
                )
                self._evict_overflow_locked(conn)
                conn.commit()
                return int(cur.lastrowid)
            except Exception:
                conn.rollback()
                raise

    def purge(self) -> int:
        """Delete all entries. Returns count removed."""
        with self._lock, self._connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM outbound_entries").fetchone()[0]
            conn.execute("DELETE FROM outbound_entries")
            return int(n)

    def evict_expired(self) -> int:
        """Drop entries older than ``ttl_seconds``. Returns count removed."""
        with self._lock, self._connect() as conn:
            return self._evict_expired_locked(conn)

    def _evict_expired_locked(self, conn: sqlite3.Connection) -> int:
        cutoff = time.time() - self.ttl_seconds
        cur = conn.execute("DELETE FROM outbound_entries WHERE ts <= ?", (cutoff,))
        return int(cur.rowcount or 0)

    def _evict_overflow_locked(self, conn: sqlite3.Connection) -> int:
        n = conn.execute("SELECT COUNT(*) FROM outbound_entries").fetchone()[0]
        if n <= self.max_size:
            return 0
        excess = n - self.max_size
        cur = conn.execute(
            "DELETE FROM outbound_entries WHERE id IN "
            "(SELECT id FROM outbound_entries ORDER BY ts ASC LIMIT ?)",
            (excess,),
        )
        return int(cur.rowcount or 0)

    def size(self) -> int:
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM outbound_entries").fetchone()[0])

    def list(self, limit: int = 100) -> List[OutboundDLQEntry]:
        """Return up to ``limit`` entries, newest first."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, platform, channel_id, reply_text,
                       thread_id, reply_to, error, attempts
                FROM outbound_entries
                ORDER BY ts DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [OutboundDLQEntry(*r) for r in rows]

    async def replay(
        self,
        handler: Callable[[OutboundDLQEntry], Awaitable[bool]],
        *,
        limit: int = 100,
    ) -> int:
        """Replay up to ``limit`` entries through ``handler``.

        Calls ``handler(entry)`` for each; if it returns ``True``,
        the entry is deleted. Otherwise increments ``attempts`` for retry.

        Returns the number of successfully replayed (deleted) entries.
        """
        import asyncio
        entries = self._list_oldest_first(limit)
        success_count = 0

        for entry in entries:
            try:
                success = await handler(entry)
                if success:
                    self._delete_entry(entry.id)
                    success_count += 1
                else:
                    self._increment_attempts(entry.id)
            except Exception as e:
                logger.warning(f"Replay handler error for entry {entry.id}: {e}")
                self._increment_attempts(entry.id)

        return success_count

    async def redeliver(
        self,
        send: Callable[[OutboundDLQEntry], Awaitable[Any]],
        *,
        limit: int = 100,
    ) -> int:
        """Boot-time drain of parked replies through ``send`` (Issue #3862).

        This is the outbound counterpart to ``InboundJournal.replay()``: the
        reply path is already durable-by-default (permanent/exhausted failures
        are parked here), but nothing re-drove those parked replies on start,
        so a reply the user is waiting for sat until an operator manually
        called :meth:`replay`. ``redeliver`` closes that gap symmetric with the
        inbound boot sweep.

        ``send(entry)`` performs the raw channel send (typically the adapter's
        own ``send_message``); a successful redelivery deletes the entry, a
        failure keeps it and increments ``attempts`` (bounded by the same TTL /
        ``max_size`` invariants). Only the *in-flight* entry's nested re-park is
        suppressed (see :meth:`enqueue_outbound`) so a re-failed send does not
        double-park **while** a genuinely-new reply that fails concurrently is
        still persisted.

        Returns the number of successfully redelivered (deleted) entries.
        """
        return await self.replay(
            lambda entry: self._redeliver_one(send, entry),
            limit=limit,
        )

    async def _redeliver_one(
        self,
        send: Callable[[OutboundDLQEntry], Awaitable[Any]],
        entry: OutboundDLQEntry,
    ) -> bool:
        # Scope the nested-park suppression to *this* entry only, so a re-failed
        # redelivery keeps its single row while unrelated concurrent failures
        # are still persisted (Issue #3862).
        self._redelivering = self._park_signature(
            entry.platform, entry.channel_id, entry.reply_text,
            entry.thread_id, entry.reply_to,
        )
        try:
            await send(entry)
            return True
        except Exception as e:  # noqa: BLE001 — keep the entry for a later boot
            logger.warning(
                "Outbound crash-recovery: redelivery of parked %s reply failed "
                "(kept for retry): %s",
                entry.platform or "bot",
                e,
            )
            return False
        finally:
            self._redelivering = None

    def _list_oldest_first(self, limit: int = 100) -> List[OutboundDLQEntry]:
        """Return up to ``limit`` entries, oldest first for replay."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, ts, platform, channel_id, reply_text,
                       thread_id, reply_to, error, attempts
                FROM outbound_entries
                ORDER BY ts ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [OutboundDLQEntry(*r) for r in rows]

    def _delete_entry(self, entry_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM outbound_entries WHERE id = ?", (entry_id,))

    def _increment_attempts(self, entry_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE outbound_entries SET attempts = attempts + 1 WHERE id = ?",
                (entry_id,),
            )

    def __repr__(self) -> str:
        return (
            f"OutboundDLQ(path={str(self.path)!r}, "
            f"size={self.size()}, "
            f"max_size={self.max_size}, ttl={self.ttl_seconds}s)"
        )


__all__ = ["InboundDLQ", "DLQEntry", "ReplayHandler", "OutboundDLQ", "OutboundDLQEntry"]
