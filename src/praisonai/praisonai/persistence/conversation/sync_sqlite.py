"""
Synchronous SQLite implementation of ConversationStore.

Provides blocking database operations using the standard sqlite3 library.
Safe for multi-agent use via per-operation connection locking.

Schema and CRUD logic live in the shared
``_sqlite_base._SQLiteConversationStoreBase``; this subclass owns only the
connection-acquisition strategy (a fresh connection per call, guarded by a
re-entrant lock) plus an explicit ``init()`` for table creation.

Example:
    store = SyncSQLiteConversationStore(path="./conversations.db")
    store.init()
"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from .base import validate_identifier
from ._sqlite_base import _SQLiteConversationStoreBase

logger = logging.getLogger(__name__)


class SyncSQLiteConversationStore(_SQLiteConversationStoreBase):
    """
    Synchronous SQLite conversation store using sqlite3.
    
    Provides blocking database operations with per-call locking
    for multi-agent safety.
    """
    
    #: This store refreshes updated_at on update for multi-agent consistency.
    _refresh_updated_at_on_update = True
    
    def __init__(
        self,
        path: str = "praisonai_conversations.db",
        table_prefix: str = "praison_",
    ):
        """
        Initialize sync SQLite store.
        
        Args:
            path: Path to SQLite database file
            table_prefix: Prefix for table names
        """
        self.path = path
        validate_identifier(table_prefix, "table_prefix")
        self.table_prefix = table_prefix
        self._lock = threading.RLock()
        self._initialized = False
    
    def init(self):
        """Initialize connection and create tables."""
        with self._lock:
            if self._initialized:
                return
            
            conn = self._new_connection()
            try:
                self._create_tables(conn)
                self._initialized = True
            finally:
                conn.close()
    
    def _new_connection(self) -> sqlite3.Connection:
        """Create a fresh sqlite3 connection with shared settings."""
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-safe connection."""
        if not self._initialized:
            self.init()
        return self._new_connection()
    
    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a fresh per-call connection under the store lock."""
        with self._lock:
            conn = self._get_connection()
            try:
                yield conn
            finally:
                conn.close()
    
    def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session (keep session metadata)."""
        return self.delete_messages(session_id) > 0
    
    def close(self) -> None:
        """No persistent connection is held; method exists for protocol compliance."""
        return None
