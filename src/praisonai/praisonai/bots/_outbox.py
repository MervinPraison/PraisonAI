"""
Outbound Message Queue for PraisonAI bot adapters.

Provides durable outbound message delivery with persistence, deduplication,
and retry mechanisms to ensure channel replies are never lost during crashes,
network failures, or restarts.

Design constraints (per PraisonAI principles):
  - Wrapper-only — heavy implementation stays out of core SDK
  - Lazy: sqlite3 is stdlib so no extra dependency
  - Optional: Adapters work exactly as before unless outbox is provided
  - Bounded: TTL + max_size prevent unbounded disk growth
  - Thread-safe: per-instance threading.Lock guards SQLite writes
  - Atomic: claim/complete mechanism ensures at-least-once delivery

Storage schema::

    outbound_queue(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL,
        idempotency_key TEXT UNIQUE,
        target TEXT,
        payload TEXT,
        metadata TEXT,
        status TEXT,  -- 'pending', 'sending', 'sent', 'failed', 'permanent_failure'
        attempts INTEGER DEFAULT 0,
        last_attempt REAL,
        error TEXT,
        sent_at REAL
    )

Public API:
  - OutboundQueue(path, *, max_size=50_000, ttl_seconds=7*86400, max_attempts=5)
  - enqueue(idempotency_key, target, payload, metadata) -> str
  - mark_sent(key)
  - mark_failed(key, error, permanent=False)
  - drain(sender) -> (succeeded, failed)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from ._resilience import BackoffPolicy, compute_backoff, is_recoverable_error

logger = logging.getLogger(__name__)

# 7 days default — long enough for debugging, short enough not to blow up disk
_DEFAULT_TTL_SECONDS = 7 * 86400
_DEFAULT_MAX_SIZE = 50_000
_DEFAULT_MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class OutboundEntry:
    """A queued outbound message."""
    
    id: int
    ts: float
    idempotency_key: str
    target: str
    payload: str
    metadata: str
    status: str
    attempts: int
    last_attempt: Optional[float]
    error: Optional[str]
    sent_at: Optional[float]


class OutboundQueue:
    """SQLite-backed outbound message queue for durable bot delivery.
    
    Implements the OutboundDeliveryProtocol from praisonaiagents.
    
    Args:
        path: SQLite file path. Created if missing; parent dirs created.
        max_size: Maximum entries kept; oldest sent entries evicted when exceeded.
        ttl_seconds: Sent entries older than this are evicted.
        max_attempts: Maximum delivery attempts before marking permanent failure.
        backoff: Backoff policy for retries.
    
    Example::
    
        from praisonai.bots import OutboundQueue, TelegramAdapter
        
        outbox = OutboundQueue(path="~/.praisonai/state/outbox.sqlite")
        adapter = TelegramAdapter(token="...")
        
        # In message handler:
        key = await outbox.enqueue("msg-123", f"telegram:{chat_id}", {"text": response})
        try:
            await adapter.send_message(chat_id, response)
            await outbox.mark_sent(key)
        except Exception as e:
            permanent = not is_recoverable_error(e, "telegram")
            await outbox.mark_failed(key, str(e), permanent)
        
        # On startup:
        async def deliver(target: str, payload: Dict[str, Any]) -> bool:
            try:
                chat_id = target.split(":")[1]
                await adapter.send_message(chat_id, payload["text"])
                return True
            except Exception as e:
                if not is_recoverable_error(e, "telegram"):
                    raise  # Will mark as permanent failure
                return False
        
        await outbox.drain(deliver)
    """
    
    def __init__(
        self,
        path: Union[str, Path],
        *,
        max_size: int = _DEFAULT_MAX_SIZE,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        backoff: Optional[BackoffPolicy] = None,
    ) -> None:
        self.path = Path(path).expanduser()
        self.max_size = int(max_size)
        self.ttl_seconds = int(ttl_seconds)
        self.max_attempts = int(max_attempts)
        self.backoff = backoff or BackoffPolicy()
        self._lock = threading.Lock()
        self._active_claims: Dict[str, float] = {}  # key -> claim_time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    # ── Schema ──────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        """Create a connection with proper context manager support."""
        conn = sqlite3.connect(str(self.path))
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
                CREATE TABLE IF NOT EXISTS outbound_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    target TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER DEFAULT 0,
                    last_attempt REAL,
                    error TEXT,
                    sent_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON outbound_queue(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON outbound_queue(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_at ON outbound_queue(sent_at)")
            
            # Reset stale 'sending' claims from previous crashes
            conn.execute("""
                UPDATE outbound_queue
                SET status = 'pending'
                WHERE status = 'sending'
            """)
            conn.commit()
    
    # ── Core API ────────────────────────────────────────────────────
    async def enqueue(
        self,
        idempotency_key: str,
        target: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist an outbound message for delivery.
        
        Args:
            idempotency_key: Unique key to prevent duplicate sends
            target: Target channel identifier (e.g., "telegram:12345")
            payload: Message payload to deliver
            metadata: Optional metadata for tracking/routing
            
        Returns:
            Unique entry key for tracking this message
        """
        if metadata is None:
            metadata = {}
        
        # Create synchronous version for thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_enqueue, idempotency_key, target, payload, metadata)
    
    def _sync_enqueue(self, idempotency_key: str, target: str, payload: Dict[str, Any], metadata: Optional[Dict[str, Any]]) -> str:
        """Synchronous version of enqueue for thread pool execution."""
        with self._lock, closing(self._connect()) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._evict_expired_locked(conn)
                
                # Try to insert - will fail on duplicate idempotency_key
                cur = conn.execute("""
                    INSERT INTO outbound_queue(ts, idempotency_key, target, 
                                              payload, metadata, status)
                    VALUES (?, ?, ?, ?, ?, 'pending')
                """, (
                    time.time(), idempotency_key, target,
                    json.dumps(payload), json.dumps(metadata)
                ))
                
                entry_id = cur.lastrowid
                self._evict_overflow_locked(conn)
                conn.commit()
                
                # Return a key for tracking operations
                return f"{target}:{idempotency_key}:{entry_id}"
                
            except sqlite3.IntegrityError:
                # Duplicate idempotency key - return existing entry
                conn.rollback()
                cur = conn.execute("""
                    SELECT id FROM outbound_queue 
                    WHERE idempotency_key = ?
                """, (idempotency_key,))
                row = cur.fetchone()
                if row:
                    return f"{target}:{idempotency_key}:{row[0]}"
                raise
            except Exception:
                conn.rollback()
                raise
    
    async def mark_sent(self, key: str) -> bool:
        """Mark a message as successfully sent."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_mark_sent, key)
    
    def _sync_mark_sent(self, key: str) -> bool:
        """Synchronous version of mark_sent for thread pool execution."""
        entry_id = self._extract_id_from_key(key)
        
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute("""
                UPDATE outbound_queue 
                SET status = 'sent', sent_at = ?
                WHERE id = ? AND status IN ('pending', 'sending', 'failed')
            """, (time.time(), entry_id))
            
            # Release active claim
            self._active_claims.pop(key, None)
            
            return cur.rowcount > 0
    
    async def mark_failed(
        self,
        key: str,
        error: str,
        permanent: bool = False,
    ) -> bool:
        """Mark a message as failed."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_mark_failed, key, error, permanent)
    
    def _sync_mark_failed(self, key: str, error: str, permanent: bool) -> bool:
        """Synchronous version of mark_failed for thread pool execution."""
        entry_id = self._extract_id_from_key(key)
        status = 'permanent_failure' if permanent else 'failed'
        
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute("""
                UPDATE outbound_queue
                SET status = ?, error = ?, last_attempt = ?, attempts = attempts + 1
                WHERE id = ?
            """, (status, error, time.time(), entry_id))
            
            # Release active claim
            self._active_claims.pop(key, None)
            
            return cur.rowcount > 0
    
    async def drain(
        self,
        sender: Callable[[str, Dict[str, Any]], Awaitable[bool]],
        limit: Optional[int] = None,
    ) -> Tuple[int, int]:
        """Process pending messages.
        
        Args:
            sender: Async function that attempts delivery
            limit: Optional max messages to process
            
        Returns:
            Tuple of (succeeded, failed) counts
        """
        # Get pending messages, oldest first
        entries = self._get_pending_entries(limit)
        succeeded = failed = 0
        
        for entry in entries:
            # Skip if we've hit max attempts
            if entry.attempts >= self.max_attempts:
                self._mark_permanent_failure(entry.id, "Max attempts exceeded")
                failed += 1
                continue
            
            # Calculate backoff delay
            if entry.last_attempt:
                delay = compute_backoff(self.backoff, entry.attempts + 1)
                time_since_last = time.time() - entry.last_attempt
                if time_since_last < delay:
                    # Not ready for retry yet
                    continue
            
            # Claim the entry to prevent concurrent processing
            key = f"{entry.target}:{entry.idempotency_key}:{entry.id}"
            if not self._claim_entry(key, entry.id):
                continue
            
            try:
                # Attempt delivery
                payload = json.loads(entry.payload)
                success = await sender(entry.target, payload)
                
                if success:
                    await self.mark_sent(key)
                    succeeded += 1
                else:
                    # Transient failure, will retry
                    await self.mark_failed(key, "Delivery returned false", permanent=False)
                    failed += 1
                    
            except Exception as e:
                # Check if error is permanent
                permanent = not is_recoverable_error(e)
                await self.mark_failed(key, str(e), permanent=permanent)
                failed += 1
                
                if permanent:
                    logger.error(f"Permanent delivery failure for {key}: {e}")
                else:
                    logger.warning(f"Transient delivery failure for {key}: {e}")
        
        return succeeded, failed
    
    # ── Internal Implementation ────────────────────────────────────
    def _claim_entry(self, key: str, entry_id: int) -> bool:
        """Claim an entry to prevent concurrent processing."""
        with self._lock:
            now = time.time()
            # Check if already claimed
            if key in self._active_claims:
                claim_age = now - self._active_claims[key]
                if claim_age < 300:  # 5 minute claim timeout
                    return False
            
            # Claim it
            self._active_claims[key] = now
            
            with closing(self._connect()) as conn:
                cur = conn.execute("""
                    UPDATE outbound_queue
                    SET status = 'sending', last_attempt = ?
                    WHERE id = ? AND status IN ('pending', 'failed')
                """, (now, entry_id))
                
                if cur.rowcount == 0:
                    # Already being processed
                    self._active_claims.pop(key, None)
                    return False
                    
            return True
    
    def _mark_permanent_failure(self, entry_id: int, error: str) -> None:
        """Mark entry as permanently failed."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                UPDATE outbound_queue
                SET status = 'permanent_failure', error = ?, last_attempt = ?
                WHERE id = ?
            """, (error, time.time(), entry_id))
    
    def _get_pending_entries(self, limit: Optional[int] = None) -> List[OutboundEntry]:
        """Get pending entries for processing."""
        with self._lock, closing(self._connect()) as conn:
            stale_claim_cutoff = time.time() - 300  # 5 minute stale claim timeout
            query = """
                SELECT id, ts, idempotency_key, target, payload, metadata,
                       status, attempts, last_attempt, error, sent_at
                FROM outbound_queue
                WHERE status IN ('pending', 'failed')
                   OR (status = 'sending' AND (last_attempt IS NULL OR last_attempt <= ?))
                ORDER BY ts ASC
            """
            params = [stale_claim_cutoff]
            
            if limit:
                query += f" LIMIT {int(limit)}"
            
            rows = conn.execute(query, params).fetchall()
            
        return [OutboundEntry(*row) for row in rows]
    
    def _extract_id_from_key(self, key: str) -> int:
        """Extract entry ID from tracking key."""
        try:
            return int(key.split(":")[-1])
        except (ValueError, IndexError):
            raise ValueError(f"Invalid entry key format: {key}")
    
    # ── Maintenance ─────────────────────────────────────────────────
    def _evict_expired_locked(self, conn: sqlite3.Connection) -> int:
        """Remove sent entries older than ttl_seconds."""
        cutoff = time.time() - self.ttl_seconds
        cur = conn.execute("""
            DELETE FROM outbound_queue 
            WHERE status = 'sent' AND sent_at <= ?
        """, (cutoff,))
        return int(cur.rowcount or 0)
    
    def _evict_overflow_locked(self, conn: sqlite3.Connection) -> int:
        """Remove oldest entries if over max_size."""
        n = conn.execute("SELECT COUNT(*) FROM outbound_queue").fetchone()[0]
        if n <= self.max_size:
            return 0
        
        excess = n - self.max_size
        
        # First try to delete old sent entries
        sent_cur = conn.execute("""
            DELETE FROM outbound_queue WHERE id IN (
                SELECT id FROM outbound_queue 
                WHERE status = 'sent'
                ORDER BY sent_at ASC 
                LIMIT ?
            )
        """, (excess,))
        deleted = int(sent_cur.rowcount or 0)
        
        # If still have excess, delete permanent failures
        remaining = excess - deleted
        if remaining > 0:
            perm_cur = conn.execute("""
                DELETE FROM outbound_queue WHERE id IN (
                    SELECT id FROM outbound_queue 
                    WHERE status = 'permanent_failure'
                    ORDER BY ts ASC 
                    LIMIT ?
                )
            """, (remaining,))
            deleted += int(perm_cur.rowcount or 0)
        
        return deleted
    
    def pending_count(self) -> int:
        """Get count of pending messages awaiting delivery."""
        with self._lock, closing(self._connect()) as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM outbound_queue WHERE status IN ('pending', 'failed')"
            ).fetchone()[0])
    
    def size(self) -> int:
        """Get total number of messages in queue."""
        with self._lock, closing(self._connect()) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM outbound_queue").fetchone()[0])
    
    async def purge_old(self, max_age_seconds: int = 86400 * 7) -> int:
        """Remove old sent messages."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_purge_old, max_age_seconds)
    
    def _sync_purge_old(self, max_age_seconds: int) -> int:
        """Synchronous version of purge_old for thread pool execution."""
        cutoff = time.time() - max_age_seconds
        
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute("""
                DELETE FROM outbound_queue 
                WHERE sent_at IS NOT NULL AND sent_at <= ?
            """, (cutoff,))
            return int(cur.rowcount or 0)
    
    def purge(self) -> int:
        """Delete all entries. Returns count removed."""
        with self._lock, closing(self._connect()) as conn:
            n = conn.execute("SELECT COUNT(*) FROM outbound_queue").fetchone()[0]
            conn.execute("DELETE FROM outbound_queue")
            conn.commit()
            return int(n)
    
    def __repr__(self) -> str:
        return (
            f"OutboundQueue(path={str(self.path)!r}, "
            f"size={self.size()}, pending={self.pending_count()}, "
            f"max_size={self.max_size}, ttl={self.ttl_seconds}s)"
        )


__all__ = ["OutboundQueue", "OutboundEntry"]