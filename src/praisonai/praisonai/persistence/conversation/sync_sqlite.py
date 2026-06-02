"""
Synchronous SQLite implementation of ConversationStore.

Provides blocking database operations using the standard sqlite3 library.
Safe for multi-agent use via per-operation connection locking.

Example:
    store = SyncSQLiteConversationStore(path="./conversations.db")
    store.init()
"""

import json
import logging
import sqlite3
import threading
import time
from typing import List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage, validate_identifier

logger = logging.getLogger(__name__)


class SyncSQLiteConversationStore(ConversationStore):
    """
    Synchronous SQLite conversation store using sqlite3.
    
    Provides blocking database operations with per-call locking
    for multi-agent safety.
    """
    
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
            
            conn = sqlite3.connect(self.path)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            
            try:
                self._create_tables(conn)
                self._initialized = True
            finally:
                conn.close()
    
    def _create_tables(self, conn: sqlite3.Connection):
        """Create database tables."""
        sessions_table = f"{self.table_prefix}sessions"
        messages_table = f"{self.table_prefix}messages"
        
        conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS {sessions_table} (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                agent_id TEXT,
                name TEXT,
                state TEXT,
                metadata TEXT,
                created_at REAL,
                updated_at REAL
            );
            
            CREATE TABLE IF NOT EXISTS {messages_table} (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                metadata TEXT,
                created_at REAL,
                FOREIGN KEY (session_id) REFERENCES {sessions_table}(session_id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_user_agent 
            ON {sessions_table}(user_id, agent_id);
            
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_session 
            ON {messages_table}(session_id, created_at);
        """)
        conn.commit()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-safe connection."""
        if not self._initialized:
            self.init()
        
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        with self._lock:
            conn = self._get_connection()
            try:
                table = f"{self.table_prefix}sessions"
                conn.execute(f"""
                    INSERT INTO {table} (session_id, user_id, agent_id, name, state, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.session_id,
                    session.user_id,
                    session.agent_id, 
                    session.name,
                    json.dumps(session.state) if session.state else None,
                    json.dumps(session.metadata) if session.metadata else None,
                    session.created_at,
                    session.updated_at
                ))
                conn.commit()
                return session
            finally:
                conn.close()
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        conn = self._get_connection()
        try:
            table = f"{self.table_prefix}sessions"
            cursor = conn.execute(f"""
                SELECT * FROM {table} WHERE session_id = ?
            """, (session_id,))
            row = cursor.fetchone()
            
            if row:
                return ConversationSession(
                    session_id=row['session_id'],
                    user_id=row['user_id'],
                    agent_id=row['agent_id'],
                    name=row['name'],
                    state=json.loads(row['state']) if row['state'] else None,
                    metadata=json.loads(row['metadata']) if row['metadata'] else None,
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
            return None
        finally:
            conn.close()
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        with self._lock:
            conn = self._get_connection()
            try:
                table = f"{self.table_prefix}sessions"
                session.updated_at = time.time()
                
                conn.execute(f"""
                    UPDATE {table} 
                    SET user_id = ?, agent_id = ?, name = ?, state = ?, metadata = ?, updated_at = ?
                    WHERE session_id = ?
                """, (
                    session.user_id,
                    session.agent_id,
                    session.name, 
                    json.dumps(session.state) if session.state else None,
                    json.dumps(session.metadata) if session.metadata else None,
                    session.updated_at,
                    session.session_id
                ))
                conn.commit()
                return session
            finally:
                conn.close()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        with self._lock:
            conn = self._get_connection()
            try:
                table = f"{self.table_prefix}sessions"
                cursor = conn.execute(f"""
                    DELETE FROM {table} WHERE session_id = ?
                """, (session_id,))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[ConversationSession]:
        """List sessions with optional filtering."""
        conn = self._get_connection()
        try:
            table = f"{self.table_prefix}sessions"
            conditions = []
            params = []
            
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            
            if agent_id:
                conditions.append("agent_id = ?")
                params.append(agent_id)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Handle pagination - SQLite requires LIMIT when OFFSET is used
            if limit is not None:
                params.append(limit)
                limit_clause = " LIMIT ?"
            elif offset is not None:
                # When offset is provided without limit, use -1 for unbounded
                params.append(-1)
                limit_clause = " LIMIT ?"
            else:
                limit_clause = ""
                
            if offset is not None:
                params.append(offset)
                offset_clause = " OFFSET ?"
            else:
                offset_clause = ""
            
            cursor = conn.execute(f"""
                SELECT * FROM {table}{where_clause}
                ORDER BY updated_at DESC{limit_clause}{offset_clause}
            """, params)
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append(ConversationSession(
                    session_id=row['session_id'],
                    user_id=row['user_id'],
                    agent_id=row['agent_id'],
                    name=row['name'],
                    state=json.loads(row['state']) if row['state'] else None,
                    metadata=json.loads(row['metadata']) if row['metadata'] else None,
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                ))
            
            return sessions
        finally:
            conn.close()
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to the conversation."""
        with self._lock:
            conn = self._get_connection()
            try:
                table = f"{self.table_prefix}messages"
                # Use the provided session_id, falling back to message.session_id if needed
                actual_session_id = session_id or message.session_id
                message.session_id = actual_session_id  # Ensure message object is consistent
                
                conn.execute(f"""
                    INSERT INTO {table} (id, session_id, role, content, tool_calls, tool_call_id, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message.id,
                    actual_session_id,
                    message.role,
                    message.content,
                    json.dumps(message.tool_calls) if message.tool_calls else None,
                    message.tool_call_id,
                    json.dumps(message.metadata) if message.metadata else None,
                    message.created_at
                ))
                conn.commit()
                return message
            finally:
                conn.close()
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Get messages for a session."""
        conn = self._get_connection()
        try:
            table = f"{self.table_prefix}messages"
            params: list = [session_id]
            conditions = []
            
            # Handle timestamp filtering
            if before is not None:
                conditions.append("created_at < ?")
                params.append(before)
                
            if after is not None:
                conditions.append("created_at > ?")
                params.append(after)
            
            # Build where clause
            timestamp_filter = " AND " + " AND ".join(conditions) if conditions else ""
            
            # Handle limit
            if limit is not None:
                params.append(limit)
                limit_clause = " LIMIT ?"
            else:
                limit_clause = ""
            
            cursor = conn.execute(f"""
                SELECT * FROM {table} WHERE session_id = ?{timestamp_filter}
                ORDER BY created_at{limit_clause}
            """, params)
            
            messages = []
            for row in cursor.fetchall():
                messages.append(ConversationMessage(
                    id=row['id'],
                    session_id=row['session_id'],
                    role=row['role'],
                    content=row['content'],
                    tool_calls=json.loads(row['tool_calls']) if row['tool_calls'] else None,
                    tool_call_id=row['tool_call_id'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else None,
                    created_at=row['created_at']
                ))
            
            return messages
        finally:
            conn.close()
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages from a session."""
        with self._lock:
            conn = self._get_connection()
            try:
                table = f"{self.table_prefix}messages"
                if message_ids is None:
                    cursor = conn.execute(f"""
                        DELETE FROM {table} WHERE session_id = ?
                    """, (session_id,))
                else:
                    placeholders = ','.join(['?' for _ in message_ids])
                    cursor = conn.execute(f"""
                        DELETE FROM {table} WHERE session_id = ? AND id IN ({placeholders})
                    """, [session_id] + message_ids)
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()
    
    def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session (keep session metadata)."""
        return self.delete_messages(session_id) > 0
    
    def close(self) -> None:
        """No persistent connection is held; method exists for protocol compliance."""
        return None