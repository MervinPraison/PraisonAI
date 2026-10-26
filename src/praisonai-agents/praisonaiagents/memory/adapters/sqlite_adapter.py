"""
SQLite Memory Adapter for PraisonAI.

Implements MemoryProtocol using SQLite as the backend.
Extracted from the main Memory class to follow protocol-driven architecture.

LAZY IMPORT: sqlite3 is only imported when this adapter is instantiated.
"""

import os
import re
import sqlite3
import json
from praisonaiagents._logging import get_logger
import threading
import weakref
from contextlib import nullcontext
from uuid import uuid4
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..protocols import MemoryProtocol

logger = get_logger(__name__)


_SEARCH_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "has", "have", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "the", "to", "was", "were", "what", "when", "where", "which", "who",
    "why", "with", "you", "your",
})


def _execute_search(conn, table, query, limit, user_id=None):
    """Match the whole query or any significant word, best matches first.

    A plain ``LIKE '%query%'`` misses natural-language queries such as
    "Which mode does the user prefer?", so rows are also matched per word and
    ranked by exact-phrase hit, then number of matched words, then recency.
    """
    terms = list(dict.fromkeys(
        w for w in re.findall(r"\w+", (query or "").lower())
        if w not in _SEARCH_STOP_WORDS
    ))[:32]  # keep well under SQLite's bound-parameter limit
    patterns = [f"%{query}%"] + [f"%{t}%" for t in terms]
    match = " OR ".join(["content LIKE ?"] * len(patterns))
    # An empty score would leave ``ORDER BY 0``, which SQLite reads as a column index
    score = " + ".join(["(content LIKE ?)"] * len(terms)) + " DESC, " if terms else ""
    user_filter = " AND memory_user_id(metadata) = ?" if user_id is not None else ""
    params = patterns + ([str(user_id)] if user_id is not None else []) + patterns + [limit]
    return conn.execute(
        f"SELECT id, content, metadata, timestamp FROM {table} "
        f"WHERE ({match}){user_filter} "
        f"ORDER BY (content LIKE ?) DESC, {score}timestamp DESC LIMIT ?",
        params,
    )


def _metadata_user_id(raw):
    """Match the existing Python JSON reader, including non-finite values."""
    try:
        metadata = json.loads(raw) if raw else {}
        return str(metadata["user_id"]) if isinstance(metadata, dict) and metadata.get("user_id") is not None else None
    except (TypeError, ValueError):
        return None


class SqliteMemoryAdapter:
    """
    SQLite-based memory adapter implementing MemoryProtocol.
    
    Features:
    - Thread-safe SQLite connections using thread-local storage
    - Separate short-term and long-term databases
    - JSON metadata storage
    - Automatic table creation
    
    Usage:
        adapter = SqliteMemoryAdapter(
            short_db="short_term.db",
            long_db="long_term.db"
        )
        result = adapter.store_short_term("Hello world", {"type": "greeting"})
    """
    
    def __init__(
        self,
        short_db: str = "short_term.db",
        long_db: str = "long_term.db",
        verbose: int = 0
    ):
        """
        Initialize SQLite memory adapter.
        
        Args:
            short_db: Path to short-term memory database
            long_db: Path to long-term memory database
            verbose: Logging verbosity level
        """
        self.short_db = short_db
        self.long_db = long_db
        self.verbose = verbose
        # Each adapter/tier owns one named in-memory database. Plain :memory:
        # would create a different database for every thread-local connection.
        self._short_target = (
            f"file:praisonai-short-{uuid4().hex}?mode=memory&cache=shared"
            if short_db == ":memory:" else short_db
        )
        self._long_target = (
            f"file:praisonai-long-{uuid4().hex}?mode=memory&cache=shared"
            if long_db == ":memory:" else long_db
        )
        
        # Thread-local storage for SQLite connections (thread-safe)
        self._local = threading.local()
        
        # Write lock for serializing database modifications (thread-safe)
        self._write_lock = threading.RLock()
        
        # Connection registry for cleanup across threads
        self._all_connections = set()
        self._connection_lock = threading.Lock()
        # Owning thread (and shared in-memory target, if any) per connection,
        # so connections of dead threads can be reclaimed
        self._connection_owners: Dict[Any, tuple] = {}
        
        # Set logger level based on verbose
        if verbose >= 5:
            logger.setLevel(10)  # DEBUG
        else:
            logger.setLevel(30)  # WARNING

    def _get_stm_conn(self):
        """Get thread-local short-term memory connection."""
        with self._write_lock if self.short_db == ":memory:" else nullcontext():
            if getattr(self._local, 'stm_conn', None) is None:
                self._local.stm_conn = sqlite3.connect(
                    self._short_target,
                    uri=self.short_db == ":memory:",
                    check_same_thread=False,
                    timeout=10.0
                )
                self._local.stm_conn.create_function("memory_user_id", 1, _metadata_user_id, deterministic=True)
                self._local.stm_conn.execute("""
                    CREATE TABLE IF NOT EXISTS short_term_memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        metadata TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                self._local.stm_conn.commit()
            
                # Register connection for cleanup
                self._register_connection(
                    self._local.stm_conn,
                    self._short_target if self.short_db == ":memory:" else None,
                )
        
            return self._local.stm_conn
    
    def _get_ltm_conn(self):
        """Get thread-local long-term memory connection."""
        with self._write_lock if self.long_db == ":memory:" else nullcontext():
            if getattr(self._local, 'ltm_conn', None) is None:
                self._local.ltm_conn = sqlite3.connect(
                    self._long_target,
                    uri=self.long_db == ":memory:",
                    check_same_thread=False,
                    timeout=10.0
                )
                self._local.ltm_conn.create_function("memory_user_id", 1, _metadata_user_id, deterministic=True)
                self._local.ltm_conn.execute("""
                    CREATE TABLE IF NOT EXISTS long_term_memory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        metadata TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                self._local.ltm_conn.commit()
            
                # Register connection for cleanup
                self._register_connection(
                    self._local.ltm_conn,
                    self._long_target if self.long_db == ":memory:" else None,
                )
        
            return self._local.ltm_conn
    
    def _register_connection(self, conn, memory_target: Optional[str] = None) -> None:
        """Track ``conn`` for cleanup and close connections of dead threads.

        Connections are thread-local, so once their owning thread exits nothing
        can reach them except this registry. Sweeping on each new registration
        keeps short-lived threads from leaking one connection (and fd) each.
        ``memory_target`` names a shared in-memory database: SQLite drops it when
        its last connection closes, so one connection to it is always kept.
        """
        with self._connection_lock:
            self._all_connections.add(conn)
            self._connection_owners[conn] = (weakref.ref(threading.current_thread()), memory_target)
            for old, (owner, target) in list(self._connection_owners.items()):
                thread = owner()
                if thread is not None and thread.is_alive():
                    continue
                if target is not None and not any(
                    t == target for c, (_, t) in self._connection_owners.items() if c is not old
                ):
                    continue
                del self._connection_owners[old]
                self._all_connections.discard(old)
                try:
                    old.close()
                except Exception:
                    pass

    def store_short_term(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Store content in short-term memory."""
        conn = self._get_stm_conn()
        with self._write_lock, conn:
            cursor = conn.execute(
                "INSERT INTO short_term_memory (content, metadata) VALUES (?, ?)",
                (text, json.dumps(metadata or {}))
            )
        return str(cursor.lastrowid)
    
    def search_short_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search short-term memory."""
        with self._write_lock if self.short_db == ":memory:" else nullcontext():
            conn = self._get_stm_conn()
            cursor = _execute_search(conn, "short_term_memory", query, limit, kwargs.get("user_id"))
        
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": str(row[0]),
                    "text": row[1],
                    "metadata": json.loads(row[2]) if row[2] else {},
                    "timestamp": row[3]
                })
        
            return results
    
    def store_long_term(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Store content in long-term memory."""
        conn = self._get_ltm_conn()
        with self._write_lock, conn:
            cursor = conn.execute(
                "INSERT INTO long_term_memory (content, metadata) VALUES (?, ?)",
                (text, json.dumps(metadata or {}))
            )
        return str(cursor.lastrowid)
    
    def search_long_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search long-term memory."""
        with self._write_lock if self.long_db == ":memory:" else nullcontext():
            conn = self._get_ltm_conn()
            cursor = _execute_search(conn, "long_term_memory", query, limit, kwargs.get("user_id"))
        
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": str(row[0]),
                    "text": row[1],
                    "metadata": json.loads(row[2]) if row[2] else {},
                    "timestamp": row[3]
                })
        
            return results
    
    def delete_memory(self, memory_id: str, tier: Optional[str] = None, **kwargs) -> bool:
        """Delete a memory by ID.

        Short-term and long-term use independent AUTOINCREMENT sequences, so an
        id like "1" typically exists in *both* tables. Pass ``tier`` ("short" or
        "long") to scope the delete to a single tier and avoid removing an
        unrelated row from the other tier. When ``tier`` is None both tiers are
        searched (legacy behaviour).
        """
        deleted = False
        with self._write_lock:
            if tier in (None, "short"):
                try:
                    stm = self._get_stm_conn()
                    with stm:
                        cur = stm.execute(
                            "DELETE FROM short_term_memory WHERE id = ?", (memory_id,)
                        )
                    if cur.rowcount > 0:
                        deleted = True
                except Exception as e:
                    logger.warning(f"Adapter delete_memory (short_term) failed: {e}")
            if tier in (None, "long"):
                try:
                    ltm = self._get_ltm_conn()
                    with ltm:
                        cur = ltm.execute(
                            "DELETE FROM long_term_memory WHERE id = ?", (memory_id,)
                        )
                    if cur.rowcount > 0:
                        deleted = True
                except Exception as e:
                    logger.warning(f"Adapter delete_memory (long_term) failed: {e}")
        return deleted

    def reset_short_term(self) -> None:
        """Clear all short-term memories."""
        conn = self._get_stm_conn()
        with self._write_lock, conn:
            conn.execute("DELETE FROM short_term_memory")

    def reset_long_term(self) -> None:
        """Clear all long-term memories."""
        conn = self._get_ltm_conn()
        with self._write_lock, conn:
            conn.execute("DELETE FROM long_term_memory")

    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all memories from both short-term and long-term."""
        # SQLite's negative LIMIT means no upper bound. Enumeration must return
        # every row; ordinary searches retain their default/explicit limits.
        short_memories = self.search_short_term("", limit=-1)
        long_memories = self.search_long_term("", limit=-1)
        
        # Mark memory types
        for memory in short_memories:
            memory["memory_type"] = "short_term"
        
        for memory in long_memories:
            memory["memory_type"] = "long_term"
        
        return short_memories + long_memories
    
    def close_connections(self):
        """Close all database connections."""
        with self._connection_lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_connections.clear()
            self._connection_owners.clear()

    def close_thread_connections(self):
        """Close only the calling thread's connections.

        Leaves the shared adapter and other threads' connections intact so the
        adapter can be reused; the calling thread lazily reopens its own
        connections on next access.

        A connection is only removed from the registry and cleared from
        thread-local storage after it closes successfully. If ``close()`` raises,
        the connection stays tracked so a later ``close_connections()`` /
        ``close_thread_connections()`` can retry it, and the failure is logged
        rather than silently swallowed.
        """
        for attr in ("stm_conn", "ltm_conn"):
            conn = getattr(self._local, attr, None)
            if conn is None:
                continue
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Failed to close {attr}; keeping it tracked for retry: {e}")
                continue
            with self._connection_lock:
                self._all_connections.discard(conn)
                self._connection_owners.pop(conn, None)
            setattr(self._local, attr, None)
