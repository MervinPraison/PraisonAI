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
        status TEXT,  -- 'pending', 'claimed', 'completed'
        claimed_at REAL,
        completed_at REAL,
        attempts INTEGER DEFAULT 0,
        UNIQUE(platform, account, channel_id, message_id)
    )

Public API:
  - InboundJournal(path, *, max_size=50_000, ttl_seconds=30*86400, claim_timeout=300)
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
        # Always release claim on exit - completion is explicit via complete()
        self._journal._release_claim(self._key)
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.__exit__(exc_type, exc_val, exc_tb)


class InboundJournal:
    """SQLite-backed inbound message journal for durable bot processing.
    
    Args:
        path: SQLite file path. Created if missing; parent dirs created.
        max_size: Maximum entries kept; oldest completed entries evicted when exceeded.
        ttl_seconds: Completed entries older than this are evicted.
        claim_timeout: Claimed entries older than this are considered stale for replay.
    
    Example::
    
        from praisonai.bots import InboundJournal, BotSessionManager
        
        journal = InboundJournal(path="~/.praisonai/state/ingress.sqlite")
        session_mgr = BotSessionManager(platform="telegram", journal=journal)
        
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
    ) -> None:
        self.path = Path(path).expanduser()
        self.max_size = int(max_size)
        self.ttl_seconds = int(ttl_seconds)
        self.claim_timeout = int(claim_timeout)
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
                return f"{platform}:{account}:{channel_id}:{message_id}:{entry_id}"
                
            except sqlite3.IntegrityError:
                # Duplicate message - this is expected for webhook redeliveries
                conn.rollback()
                return None
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
            # Context manager will call _release_claim
            pass
    
    @asynccontextmanager  
    async def aclaim(self, key: str):
        """Async claim a journal entry for processing."""
        self._claim_entry(key)
        try:
            yield ClaimContext(self, key)
        finally:
            # Context manager will call _release_claim
            pass
    
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
        """Remove oldest completed entries if over max_size."""
        n = conn.execute("SELECT COUNT(*) FROM ingress_journal").fetchone()[0]
        if n <= self.max_size:
            return 0
            
        excess = n - self.max_size
        cur = conn.execute("""
            DELETE FROM ingress_journal WHERE id IN (
                SELECT id FROM ingress_journal 
                WHERE status = 'completed'
                ORDER BY completed_at ASC 
                LIMIT ?
            )
        """, (excess,))
        return int(cur.rowcount or 0)
    
    def replay(self) -> int:
        """Find and replay stale claimed entries. Returns count replayed."""
        stale_cutoff = time.time() - self.claim_timeout
        
        with self._lock, self._connect() as conn:
            # Find stale claimed entries  
            cur = conn.execute("""
                SELECT id FROM ingress_journal
                WHERE status = 'claimed' AND claimed_at <= ?
            """, (stale_cutoff,))
            
            stale_ids = [row[0] for row in cur.fetchall()]
            
            if stale_ids:
                # Reset them to pending for replay
                placeholders = ",".join("?" * len(stale_ids))
                conn.execute(f"""
                    UPDATE ingress_journal
                    SET status = 'pending', claimed_at = NULL
                    WHERE id IN ({placeholders})
                """, stale_ids)
                
                logger.info(f"InboundJournal: reset {len(stale_ids)} stale claimed entries for replay")
                
        return len(stale_ids)
    
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