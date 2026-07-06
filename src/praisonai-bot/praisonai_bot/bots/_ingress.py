"""
Inbound Message Journal for PraisonAI bot adapters.

Provides durable inbound message processing with deduplication, persistent
ingress journal, and idempotent replay to prevent duplicate agent runs and
silent message loss during crashes or webhook redeliveries.

Design constraints (per PraisonAI principles):
  - Wrapper-only — heavy implementation stays out of core SDK
  - Lazy: sqlite3 is stdlib so no extra dependency  
  - Optional: BotSessionManager works exactly as before unless journal is provided
  - Bounded: TTL + max_size prevent unbounded disk growth
  - Thread-safe: per-instance threading.Lock guards SQLite writes
  - Atomic: claim/complete mechanism ensures at-least-once with effective exactly-once

Storage schema::

    ingress_journal(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL,
        platform TEXT, 
        account TEXT,
        channel_id TEXT, 
        message_id TEXT,
        payload TEXT,
        status TEXT,  -- 'pending', 'claimed', 'completed', 'quarantined'
        claimed_at REAL,
        completed_at REAL,
        attempts INTEGER DEFAULT 0,
        UNIQUE(platform, account, channel_id, message_id)
    )

Poison-message quarantine: an inbound entry that repeatedly fails to
complete (e.g. it crashes the process during handling) is re-claimed on
each boot. To avoid an infinite boot->replay->crash loop, ``replay()``
caps ``attempts`` at ``max_attempts``; once exhausted the entry is routed
to an optional ``InboundDLQ`` and marked ``quarantined`` instead of being
reset to ``pending``. This mirrors the outbound ``OutboundQueue``
``permanent_failure`` semantics.

Public API:
  - InboundJournal(path, *, max_size=50_000, ttl_seconds=30*86400,
                   claim_timeout=300, max_attempts=5, dlq=None)
  - receive(platform, account, channel_id, message_id, payload) -> Optional[str]
  - claim(key) -> ClaimContext  
  - complete(key)
  - replay() -> int
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# 30 days default — long enough for ops to investigate, short enough not to blow up disk
_DEFAULT_TTL_SECONDS = 30 * 86400
_DEFAULT_MAX_SIZE = 50_000
_DEFAULT_CLAIM_TIMEOUT = 300  # 5 minutes
# Cap on inbound claim attempts before an entry is quarantined. Mirrors the
# outbound queue's max_attempts so a poison message cannot loop the gateway.
_DEFAULT_MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class JournalEntry:
    """A journaled inbound message."""
    
    id: int
    ts: float
    platform: str
    account: str  
    channel_id: str
    message_id: str
    payload: str
    status: str
    claimed_at: Optional[float]
    completed_at: Optional[float]  
    attempts: int


class ClaimContext:
    """Context manager for claiming/releasing journal entries."""
    
    def __init__(self, journal: "InboundJournal", key: str):
        self._journal = journal
        self._key = key
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # No longer needed - release is handled by the outer context managers
        pass
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # No longer needed - release is handled by the outer context managers
        pass


class InboundJournal:
    """SQLite-backed inbound message journal for durable bot processing.
    
    Args:
        path: SQLite file path. Created if missing; parent dirs created.
        max_size: Maximum entries kept; oldest completed entries evicted when exceeded.
        ttl_seconds: Completed entries older than this are evicted.
        claim_timeout: Claimed entries older than this are considered stale for replay.
        max_attempts: Maximum claim attempts before an entry is quarantined
            instead of replayed. Prevents a poison message from looping the
            gateway forever. Mirrors the outbound queue's ``max_attempts``.
        dlq: Optional ``InboundDLQ`` (or any object with a compatible
            ``enqueue(...)``). Quarantined entries are routed here so an
            operator can inspect or replay them. If ``None``, exhausted
            entries are still marked ``quarantined`` (never replayed) but not
            copied to a dead-letter store.
    
    Example::
    
        from praisonai_bot.bots import InboundJournal, BotSessionManager
        
        journal = InboundJournal(path="~/.praisonai/state/ingress.sqlite")
        session_mgr = BotSessionManager(platform="telegram", ingress_journal=journal)
        
        # In message handler:
        key = journal.receive("telegram", "bot123", chat_id, update.message.message_id, payload)
        if key is None:
            return  # duplicate redelivery
        async with journal.claim(key):
            response = await session_mgr.chat(agent, user_id, text)
        journal.complete(key)
    """
    
    def __init__(
        self,
        path: Union[str, Path],
        *,
        max_size: int = _DEFAULT_MAX_SIZE,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        claim_timeout: int = _DEFAULT_CLAIM_TIMEOUT,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        dlq: Optional[Any] = None,
    ) -> None:
        self.path = Path(path).expanduser()
        self.max_size = int(max_size)
        self.ttl_seconds = int(ttl_seconds)
        self.claim_timeout = int(claim_timeout)
        self.max_attempts = max(1, int(max_attempts))
        self._dlq = dlq
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingress_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    platform TEXT NOT NULL,
                    account TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL, 
                    payload TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    claimed_at REAL,
                    completed_at REAL,
                    attempts INTEGER DEFAULT 0,
                    UNIQUE(platform, account, channel_id, message_id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON ingress_journal(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON ingress_journal(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_claimed_at ON ingress_journal(claimed_at)")
    
    # ── Core API ────────────────────────────────────────────────────
    def receive(
        self,
        platform: str,
        account: str,  
        channel_id: str,
        message_id: str,
        payload: Dict[str, Any] = None
    ) -> Optional[str]:
        """Journal an inbound message for durable processing.
        
        Args:
            platform: Bot platform ("telegram", "discord", "slack", etc.)
            account: Bot account/instance identifier  
            channel_id: Platform channel/chat identifier
            message_id: Platform message identifier
            payload: Message data to store (will be JSON-serialized)
            
        Returns:
            str: Unique key for claim/complete, or None if duplicate
        """
        if payload is None:
            payload = {}
            
        with self._lock, self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._evict_expired_locked(conn)
                
                # Try to insert - will fail on duplicate (platform, account, channel_id, message_id)
                cur = conn.execute("""
                    INSERT INTO ingress_journal(ts, platform, account, channel_id, 
                                               message_id, payload, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """, (
                    time.time(), platform, account, channel_id, 
                    message_id, json.dumps(payload)
                ))
                
                entry_id = cur.lastrowid
                self._evict_overflow_locked(conn)
                conn.commit()
                
                # Return a key for claim/complete operations
                return self._make_key(
                    platform, account, channel_id, message_id, entry_id
                )
                
            except sqlite3.IntegrityError:
                # Duplicate message_id — return key only if still unprocessed
                conn.rollback()
                return self._key_for_existing_locked(
                    conn, platform, account, channel_id, message_id
                )
            except Exception:
                conn.rollback() 
                raise
    
    @contextmanager
    def claim(self, key: str):
        """Claim a journal entry for processing."""
        self._claim_entry(key)
        try:
            yield ClaimContext(self, key)
        finally:
            # Release claim if not completed
            self._release_claim(key)
    
    @asynccontextmanager  
    async def aclaim(self, key: str):
        """Async claim a journal entry for processing."""
        self._claim_entry(key)
        try:
            yield ClaimContext(self, key)
        finally:
            # Release claim if not completed
            self._release_claim(key)
    
    def complete(self, key: str) -> None:
        """Mark a journal entry as completed."""
        entry_id = self._extract_id_from_key(key)
        
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE ingress_journal 
                SET status = 'completed', completed_at = ?
                WHERE id = ?
            """, (time.time(), entry_id))
    
    # ── Internal Implementation ────────────────────────────────────
    def _claim_entry(self, key: str) -> None:
        """Mark entry as claimed for processing."""
        entry_id = self._extract_id_from_key(key)
        
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE ingress_journal
                SET status = 'claimed', claimed_at = ?, attempts = attempts + 1
                WHERE id = ? AND status IN ('pending', 'claimed')
            """, (time.time(), entry_id))
    
    def _release_claim(self, key: str) -> None:
        """Release claim without completing (for crash recovery)."""
        entry_id = self._extract_id_from_key(key)
        
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE ingress_journal
                SET status = 'pending', claimed_at = NULL
                WHERE id = ? AND status = 'claimed'
            """, (entry_id,))
    
    def _extract_id_from_key(self, key: str) -> int:
        """Extract entry ID from journal key."""
        try:
            return int(key.split(":")[-1])
        except (ValueError, IndexError):
            raise ValueError(f"Invalid journal key format: {key}")

    def _make_key(
        self,
        platform: str,
        account: str,
        channel_id: str,
        message_id: str,
        entry_id: int,
    ) -> str:
        return f"{platform}:{account}:{channel_id}:{message_id}:{entry_id}"

    def _key_for_existing_locked(
        self,
        conn: sqlite3.Connection,
        platform: str,
        account: str,
        channel_id: str,
        message_id: str,
    ) -> Optional[str]:
        """Return journal key for an uncompleted duplicate (caller holds lock)."""
        row = conn.execute(
            """
            SELECT id, status, claimed_at, attempts FROM ingress_journal
            WHERE platform = ? AND account = ? AND channel_id = ? AND message_id = ?
            """,
            (platform, account, channel_id, message_id),
        ).fetchone()
        if not row:
            return None

        entry_id, status, claimed_at, attempts = row
        # Completed or already quarantined (poison) entries are never
        # reprocessed on redelivery.
        if status in ("completed", "quarantined"):
            return None

        if status == "claimed" and claimed_at is not None:
            if time.time() - claimed_at <= self.claim_timeout:
                return None
            # Stale claim: quarantine instead of re-offering if the entry has
            # already exhausted its attempts, so a redelivered poison message
            # cannot bypass the replay-path cap.
            if attempts >= self.max_attempts:
                conn.execute(
                    """
                    UPDATE ingress_journal
                    SET status = 'quarantined', claimed_at = NULL
                    WHERE id = ?
                    """,
                    (entry_id,),
                )
                conn.commit()
                return None
            conn.execute(
                """
                UPDATE ingress_journal
                SET status = 'pending', claimed_at = NULL
                WHERE id = ?
                """,
                (entry_id,),
            )
            conn.commit()

        return self._make_key(platform, account, channel_id, message_id, entry_id)

    def _key_for_existing(
        self,
        platform: str,
        account: str,
        channel_id: str,
        message_id: str,
    ) -> Optional[str]:
        """Return journal key for an uncompleted duplicate, else None if done/in-flight."""
        with self._lock, self._connect() as conn:
            return self._key_for_existing_locked(
                conn, platform, account, channel_id, message_id
            )
    
    # ── Maintenance ─────────────────────────────────────────────────
    def _evict_expired_locked(self, conn: sqlite3.Connection) -> int:
        """Remove completed entries older than ttl_seconds."""
        cutoff = time.time() - self.ttl_seconds
        cur = conn.execute("""
            DELETE FROM ingress_journal 
            WHERE status = 'completed' AND completed_at <= ?
        """, (cutoff,))
        return int(cur.rowcount or 0)
    
    def _evict_overflow_locked(self, conn: sqlite3.Connection) -> int:
        """Remove oldest entries if over max_size. Prefers completed, then oldest pending."""
        n = conn.execute("SELECT COUNT(*) FROM ingress_journal").fetchone()[0]
        if n <= self.max_size:
            return 0
            
        excess = n - self.max_size
        
        # First try to delete completed entries
        completed_cur = conn.execute("""
            DELETE FROM ingress_journal WHERE id IN (
                SELECT id FROM ingress_journal 
                WHERE status = 'completed'
                ORDER BY completed_at ASC 
                LIMIT ?
            )
        """, (excess,))
        deleted = int(completed_cur.rowcount or 0)
        
        # If we still have excess after deleting completed entries, delete oldest pending
        remaining_excess = excess - deleted
        if remaining_excess > 0:
            pending_cur = conn.execute("""
                DELETE FROM ingress_journal WHERE id IN (
                    SELECT id FROM ingress_journal 
                    WHERE status = 'pending'
                    ORDER BY ts ASC 
                    LIMIT ?
                )
            """, (remaining_excess,))
            deleted += int(pending_cur.rowcount or 0)
            
        return deleted
    
    def replay(self) -> int:
        """Find and replay stale claimed entries. Returns count replayed.

        Entries whose ``attempts`` have reached ``max_attempts`` are NOT
        reset to ``pending``. Instead they are routed to the optional
        ``InboundDLQ`` and marked ``quarantined`` so a poison message can
        never loop the gateway forever. This mirrors the outbound queue's
        ``attempts >= max_attempts -> permanent_failure`` behaviour.

        Returns the number of entries reset to ``pending`` for replay
        (quarantined entries are excluded from the count).
        """
        stale_cutoff = time.time() - self.claim_timeout

        replay_ids: List[int] = []
        quarantine_ids: List[int] = []
        quarantine_entries: List[JournalEntry] = []

        with self._lock, self._connect() as conn:
            # Find stale claimed entries, capturing attempts to decide fate.
            cur = conn.execute("""
                SELECT id, ts, platform, account, channel_id, message_id,
                       payload, status, claimed_at, completed_at, attempts
                FROM ingress_journal
                WHERE status = 'claimed' AND claimed_at <= ?
            """, (stale_cutoff,))
            stale = [JournalEntry(*row) for row in cur.fetchall()]

            for entry in stale:
                if entry.attempts >= self.max_attempts:
                    quarantine_ids.append(entry.id)
                    quarantine_entries.append(entry)
                else:
                    replay_ids.append(entry.id)

            if replay_ids:
                placeholders = ",".join("?" * len(replay_ids))
                conn.execute(f"""
                    UPDATE ingress_journal
                    SET status = 'pending', claimed_at = NULL
                    WHERE id IN ({placeholders})
                """, replay_ids)
                logger.info(
                    "InboundJournal: reset %d stale claimed entries for replay",
                    len(replay_ids),
                )

            if quarantine_ids:
                placeholders = ",".join("?" * len(quarantine_ids))
                conn.execute(f"""
                    UPDATE ingress_journal
                    SET status = 'quarantined', claimed_at = NULL
                    WHERE id IN ({placeholders})
                """, quarantine_ids)
                logger.warning(
                    "InboundJournal: quarantined %d poison entries after %d attempts",
                    len(quarantine_ids), self.max_attempts,
                )

        # Route quarantined entries to the DLQ outside the journal lock so we
        # never hold two store locks at once (the DLQ has its own lock).
        for entry in quarantine_entries:
            self._route_to_dlq(entry)

        return len(replay_ids)

    def _route_to_dlq(self, entry: JournalEntry) -> None:
        """Best-effort copy of a quarantined entry into the inbound DLQ."""
        if self._dlq is None:
            return
        try:
            payload = json.loads(entry.payload) if entry.payload else {}
        except (ValueError, TypeError):
            payload = {}
        try:
            self._dlq.enqueue(
                platform=entry.platform,
                user_id=str(payload.get("user_id", entry.channel_id)),
                prompt=str(payload.get("text", payload.get("prompt", entry.payload))),
                error=f"Max inbound attempts exceeded ({entry.attempts})",
                chat_id=str(entry.channel_id),
                thread_id=str(payload.get("thread_id", "")),
                user_name=str(payload.get("user_name", "")),
            )
        except Exception as e:  # pragma: no cover — defensive, DLQ is best-effort
            logger.warning(
                "InboundJournal: failed to route quarantined entry %d to DLQ: %s",
                entry.id, e,
            )

    def quarantined_count(self) -> int:
        """Return number of quarantined (poison) entries awaiting review."""
        with self._lock, self._connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM ingress_journal WHERE status = 'quarantined'"
            ).fetchone()[0])
    
    def size(self) -> int:
        """Return total number of entries."""
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM ingress_journal").fetchone()[0])
    
    def pending_count(self) -> int:
        """Return number of pending entries."""  
        with self._lock, self._connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM ingress_journal WHERE status = 'pending'"
            ).fetchone()[0])
    
    def purge(self) -> int:
        """Delete all entries. Returns count removed."""
        with self._lock, self._connect() as conn:
            n = conn.execute("SELECT COUNT(*) FROM ingress_journal").fetchone()[0]
            conn.execute("DELETE FROM ingress_journal")
            return int(n)
    
    def __repr__(self) -> str:
        return (
            f"InboundJournal(path={str(self.path)!r}, "
            f"size={self.size()}, pending={self.pending_count()}, "
            f"max_size={self.max_size}, ttl={self.ttl_seconds}s)"
        )


__all__ = ["InboundJournal", "JournalEntry", "ClaimContext"]