"""
SQLite implementation of ConversationStore.

Zero external dependencies - uses built-in sqlite3 module.

Uses a shared (thread-local) connection. Schema and CRUD logic live in the
shared ``_sqlite_base._SQLiteConversationStoreBase``; this subclass owns only
the connection-acquisition strategy.
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from .base import validate_identifier
from ._sqlite_base import _SQLiteConversationStoreBase

logger = logging.getLogger(__name__)


class SQLiteConversationStore(_SQLiteConversationStoreBase):
    """
    SQLite-based conversation store.
    
    Zero external dependencies - uses Python's built-in sqlite3.
    
    Example:
        store = SQLiteConversationStore(
            path="./praisonai.db"
        )
    """
    
    def __init__(
        self,
        path: str = "praisonai_conversations.db",
        table_prefix: str = "praison_",
        auto_create_tables: bool = True,
        check_same_thread: bool = False,
    ):
        """
        Initialize SQLite conversation store.
        
        Args:
            path: Path to SQLite database file
            table_prefix: Prefix for table names
            auto_create_tables: Create tables if they don't exist
            check_same_thread: SQLite check_same_thread parameter
        """
        self.path = path
        validate_identifier(table_prefix, "table_prefix")
        self.table_prefix = table_prefix
        self._check_same_thread = check_same_thread
        self._local = threading.local()
        # Track every thread-local connection so close() can drain them all.
        # threading.local() is per-thread by definition, so without this the
        # caller thread's close() would leak every other worker's connection
        # (fd + SQLite memory arena) in a long-lived thread pool.
        self._conns_lock = threading.Lock()
        self._conns: list[sqlite3.Connection] = []
        
        if auto_create_tables:
            self._create_tables(self._get_conn())
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(
                self.path,
                check_same_thread=self._check_same_thread
            )
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
            with self._conns_lock:
                self._conns.append(conn)
        return self._local.conn
    
    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield the shared thread-local connection (kept open across calls).

        Rolls back any uncommitted transaction if an exception escapes so the
        persistent connection is not left in a stale, partially-applied state.
        """
        conn = self._get_conn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
    
    def close(self) -> None:
        """Close the store, draining every thread's connection.

        Closes all tracked connections (not just the caller thread's slot) so a
        ``store.close()`` from the main thread does not leak the N-1 worker
        connections opened across a thread pool.

        When ``check_same_thread=True`` a connection created on another thread
        cannot be closed from here — SQLite raises ``ProgrammingError``. Such a
        connection is *kept* in the tracking list (not silently dropped) so it
        stays reachable for a later ``close()`` from its owning thread instead
        of leaking untracked. Connections that close cleanly are removed.
        """
        with self._conns_lock:
            unclosed: list[sqlite3.Connection] = []
            for conn in self._conns:
                try:
                    conn.close()
                except sqlite3.ProgrammingError:
                    # Thread-affine (check_same_thread=True) connection owned by
                    # another thread — keep it tracked so its owner can close it.
                    unclosed.append(conn)
                except sqlite3.Error:
                    pass
            self._conns[:] = unclosed
        # Best-effort clear of the caller's own thread-local slot.
        if hasattr(self._local, "conn"):
            self._local.conn = None
