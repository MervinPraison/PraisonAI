"""
SQLite implementation of ConversationStore.

Zero external dependencies - uses built-in sqlite3 module.
"""

import json
import logging
import sqlite3
import threading
from typing import Any, List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class SQLiteConversationStore(ConversationStore):
    """
    SQLite-based conversation store.
    
    Zero external dependencies - uses Python's built-in sqlite3.
    
    Example:
        store = SQLiteConversationStore(
            path="./praisonai.db"
        )
    """
    
    SCHEMA_VERSION = "1.0.0"
    
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
        self.table_prefix = table_prefix
        self.sessions_table = f"{table_prefix}sessions"
        self.messages_table = f"{table_prefix}messages"
        self._check_same_thread = check_same_thread
        self._local = threading.local()
        
        if auto_create_tables:
            self._create_tables()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.path,
                check_same_thread=self._check_same_thread
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
    
    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        # Sessions table
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.sessions_table} (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                agent_id TEXT,
                name TEXT,
                state TEXT,
                metadata TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)
        
        # Sessions indexes
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_user 
            ON {self.sessions_table}(user_id)
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_agent 
            ON {self.sessions_table}(agent_id)
        """)
        
        # Messages table
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.messages_table} (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                metadata TEXT,
                created_at REAL,
                FOREIGN KEY (session_id) REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE
            )
        """)
        
        # Messages indexes
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_session 
            ON {self.messages_table}(session_id)
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_created 
            ON {self.messages_table}(session_id, created_at)
        """)
        
        # Enable foreign keys
        cur.execute("PRAGMA foreign_keys = ON")
        
        conn.commit()
        logger.info(f"SQLite tables created: {self.sessions_table}, {self.messages_table}")
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO {self.sessions_table} 
            (session_id, user_id, agent_id, name, state, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.session_id,
            session.user_id,
            session.agent_id,
            session.name,
            json.dumps(session.state) if session.state else None,
            json.dumps(session.metadata) if session.metadata else None,
            session.created_at,
            session.updated_at,
        ))
        conn.commit()
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM {self.sessions_table} WHERE session_id = ?
        """, (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        return ConversationSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            name=row["name"],
            state=json.loads(row["state"]) if row["state"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE {self.sessions_table}
            SET user_id = ?, agent_id = ?, name = ?, 
                state = ?, metadata = ?, updated_at = ?
            WHERE session_id = ?
        """, (
            session.user_id,
            session.agent_id,
            session.name,
            json.dumps(session.state) if session.state else None,
            json.dumps(session.metadata) if session.metadata else None,
            session.updated_at,
            session.session_id,
        ))
        conn.commit()
        return session
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        conn = self._get_conn()
        cur = conn.cursor()
        # Delete messages first (foreign key)
        cur.execute(f"DELETE FROM {self.messages_table} WHERE session_id = ?", (session_id,))
        cur.execute(f"DELETE FROM {self.sessions_table} WHERE session_id = ?", (session_id,))
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """List sessions, optionally filtered by user or agent."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        conditions = []
        params: List[Any] = []
        
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        params.extend([limit, offset])
        
        cur.execute(f"""
            SELECT * FROM {self.sessions_table}
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """, params)
        
        return [
            ConversationSession(
                session_id=row["session_id"],
                user_id=row["user_id"],
                agent_id=row["agent_id"],
                name=row["name"],
                state=json.loads(row["state"]) if row["state"] else None,
                metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in cur.fetchall()
        ]
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a session."""
        message.session_id = session_id
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO {self.messages_table}
            (id, session_id, role, content, tool_calls, tool_call_id, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message.id,
            session_id,
            message.role,
            message.content,
            json.dumps(message.tool_calls) if message.tool_calls else None,
            message.tool_call_id,
            json.dumps(message.metadata) if message.metadata else None,
            message.created_at,
        ))
        conn.commit()
        return message
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Get messages from a session."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        conditions = ["session_id = ?"]
        params: List[Any] = [session_id]
        
        if before:
            conditions.append("created_at < ?")
            params.append(before)
        if after:
            conditions.append("created_at > ?")
            params.append(after)
        
        where_clause = "WHERE " + " AND ".join(conditions)
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        cur.execute(f"""
            SELECT * FROM {self.messages_table}
            {where_clause}
            ORDER BY created_at ASC
            {limit_clause}
        """, params)
        
        return [
            ConversationMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
                tool_call_id=row["tool_call_id"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else None,
                created_at=row["created_at"],
            )
            for row in cur.fetchall()
        ]
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        if message_ids:
            placeholders = ",".join(["?"] * len(message_ids))
            cur.execute(f"""
                DELETE FROM {self.messages_table}
                WHERE session_id = ? AND id IN ({placeholders})
            """, [session_id] + message_ids)
        else:
            cur.execute(f"""
                DELETE FROM {self.messages_table} WHERE session_id = ?
            """, (session_id,))
        
        deleted = cur.rowcount
        conn.commit()
        return deleted
    
    def close(self) -> None:
        """Close the store."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
