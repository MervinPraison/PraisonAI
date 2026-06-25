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
        
        if auto_create_tables:
            self._create_tables(self._get_conn())
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.path,
                check_same_thread=self._check_same_thread
            )
            self._local.conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn.row_factory = sqlite3.Row
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
        """Close the store."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
