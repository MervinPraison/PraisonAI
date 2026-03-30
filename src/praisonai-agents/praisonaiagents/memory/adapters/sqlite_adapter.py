"""
SQLite Memory Adapter for PraisonAI.

Implements MemoryProtocol using SQLite as the backend.
Extracted from the main Memory class to follow protocol-driven architecture.

LAZY IMPORT: sqlite3 is only imported when this adapter is instantiated.
"""

import os
import sqlite3
import json
import logging
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime

from ..protocols import MemoryProtocol

logger = logging.getLogger(__name__)


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
        
        # Thread-local storage for SQLite connections (thread-safe)
        self._local = threading.local()
        
        # Write lock for serializing database modifications (thread-safe)
        self._write_lock = threading.Lock()
        
        # Connection registry for cleanup across threads
        self._all_connections = set()
        self._connection_lock = threading.Lock()
        
        # Set logger level based on verbose
        if verbose >= 5:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)
    
    def _get_stm_conn(self):
        """Get thread-local short-term memory connection."""
        if not hasattr(self._local, 'stm_conn'):
            self._local.stm_conn = sqlite3.connect(
                self.short_db,
                check_same_thread=False,
                timeout=10.0
            )
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
            with self._connection_lock:
                self._all_connections.add(self._local.stm_conn)
        
        return self._local.stm_conn
    
    def _get_ltm_conn(self):
        """Get thread-local long-term memory connection."""
        if not hasattr(self._local, 'ltm_conn'):
            self._local.ltm_conn = sqlite3.connect(
                self.long_db,
                check_same_thread=False,
                timeout=10.0
            )
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
            with self._connection_lock:
                self._all_connections.add(self._local.ltm_conn)
        
        return self._local.ltm_conn
    
    def store_short_term(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Store content in short-term memory."""
        conn = self._get_stm_conn()
        with self._write_lock:
            cursor = conn.execute(
                "INSERT INTO short_term_memory (content, metadata) VALUES (?, ?)",
                (text, json.dumps(metadata or {}))
            )
            conn.commit()
            return str(cursor.lastrowid)
    
    def search_short_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search short-term memory."""
        conn = self._get_stm_conn()
        cursor = conn.execute(
            "SELECT id, content, metadata, timestamp FROM short_term_memory "
            "WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{query}%", limit)
        )
        
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
        with self._write_lock:
            cursor = conn.execute(
                "INSERT INTO long_term_memory (content, metadata) VALUES (?, ?)",
                (text, json.dumps(metadata or {}))
            )
            conn.commit()
            return str(cursor.lastrowid)
    
    def search_long_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search long-term memory."""
        conn = self._get_ltm_conn()
        cursor = conn.execute(
            "SELECT id, content, metadata, timestamp FROM long_term_memory "
            "WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{query}%", limit)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": str(row[0]),
                "text": row[1],
                "metadata": json.loads(row[2]) if row[2] else {},
                "timestamp": row[3]
            })
        
        return results
    
    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all memories from both short-term and long-term."""
        short_memories = self.search_short_term("", limit=1000)
        long_memories = self.search_long_term("", limit=1000)
        
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