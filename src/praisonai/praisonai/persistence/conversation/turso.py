"""
Turso/libSQL implementation of ConversationStore.

Requires: libsql
Install: pip install libsql
"""

import json
import logging
import os
from typing import List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)

try:
    import libsql
except ImportError:
    libsql = None


class TursoConversationStore(ConversationStore):
    """
    Turso/libSQL-based conversation store.
    
    Uses Turso's SQLite-compatible edge database with optional embedded replicas.
    
    Example:
        store = TursoConversationStore(
            url="libsql://mydb-user.turso.io",
            auth_token="eyJ..."
        )
    """
    
    SCHEMA_VERSION = "1.0.0"
    
    def __init__(
        self,
        url: Optional[str] = None,
        auth_token: Optional[str] = None,
        local_path: str = "praisonai_turso.db",
        table_prefix: str = "praison_",
        auto_create_tables: bool = True,
        sync_on_write: bool = True,
    ):
        """
        Initialize Turso conversation store.
        
        Args:
            url: Turso database URL (libsql://...)
            auth_token: Turso authentication token
            local_path: Local SQLite file for embedded replica
            table_prefix: Prefix for table names
            auto_create_tables: Create tables if they don't exist
            sync_on_write: Sync to remote after writes (embedded replica mode)
        """
        if libsql is None:
            raise ImportError(
                "libsql is required for Turso support. "
                "Install with: pip install libsql"
            )
        
        self._url = url or os.getenv("TURSO_DATABASE_URL")
        self._auth_token = auth_token or os.getenv("TURSO_AUTH_TOKEN")
        self.table_prefix = table_prefix
        self.sessions_table = f"{table_prefix}sessions"
        self.messages_table = f"{table_prefix}messages"
        self._sync_on_write = sync_on_write
        
        # Connect — remote or embedded replica
        if self._url and self._auth_token:
            self._conn = libsql.connect(
                local_path,
                sync_url=self._url,
                auth_token=self._auth_token,
            )
            # Initial sync from remote
            self._conn.sync()
            logger.info(f"Turso connected (embedded replica): {self._url}")
        elif self._url:
            # Remote-only (no local replica)
            self._conn = libsql.connect(
                local_path,
                sync_url=self._url,
                auth_token=self._auth_token or "",
            )
            logger.info(f"Turso connected (remote): {self._url}")
        else:
            # Local-only mode (useful for testing)
            self._conn = libsql.connect(local_path)
            self._sync_on_write = False
            logger.info(f"Turso connected (local only): {local_path}")
        
        if auto_create_tables:
            self._create_tables()
    
    def _sync(self):
        """Sync local replica to remote if in embedded replica mode."""
        if self._sync_on_write:
            try:
                self._conn.sync()
            except Exception as e:
                logger.warning(f"Turso sync failed: {e}")
    
    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        cur = self._conn.cursor()
        
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
        
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_user 
            ON {self.sessions_table}(user_id)
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_agent 
            ON {self.sessions_table}(agent_id)
        """)
        
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.messages_table} (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL
                    REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                metadata TEXT,
                created_at REAL
            )
        """)
        
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_session 
            ON {self.messages_table}(session_id)
        """)
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_created 
            ON {self.messages_table}(session_id, created_at)
        """)
        
        self._conn.commit()
        self._sync()
        logger.info(f"Turso tables created: {self.sessions_table}, {self.messages_table}")
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        cur = self._conn.cursor()
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
        self._conn.commit()
        self._sync()
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        cur = self._conn.cursor()
        cur.execute(f"""
            SELECT session_id, user_id, agent_id, name, state, metadata, created_at, updated_at
            FROM {self.sessions_table} WHERE session_id = ?
        """, (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        return ConversationSession(
            session_id=row[0],
            user_id=row[1],
            agent_id=row[2],
            name=row[3],
            state=json.loads(row[4]) if row[4] else None,
            metadata=json.loads(row[5]) if row[5] else None,
            created_at=row[6],
            updated_at=row[7],
        )
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        cur = self._conn.cursor()
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
        self._conn.commit()
        self._sync()
        return session
    
    def delete_session(self, session_id: str) -> bool:
        cur = self._conn.cursor()
        # Delete messages first (FK)
        cur.execute(f"DELETE FROM {self.messages_table} WHERE session_id = ?", (session_id,))
        cur.execute(f"DELETE FROM {self.sessions_table} WHERE session_id = ?", (session_id,))
        deleted = cur.rowcount > 0
        self._conn.commit()
        self._sync()
        return deleted
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        conditions = []
        params: list = []
        
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
        
        cur = self._conn.cursor()
        cur.execute(f"""
            SELECT session_id, user_id, agent_id, name, state, metadata, created_at, updated_at
            FROM {self.sessions_table}
            {where_clause}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """, params)
        
        return [
            ConversationSession(
                session_id=row[0],
                user_id=row[1],
                agent_id=row[2],
                name=row[3],
                state=json.loads(row[4]) if row[4] else None,
                metadata=json.loads(row[5]) if row[5] else None,
                created_at=row[6],
                updated_at=row[7],
            )
            for row in cur.fetchall()
        ]
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        message.session_id = session_id
        cur = self._conn.cursor()
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
        self._conn.commit()
        self._sync()
        return message
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        conditions = ["session_id = ?"]
        params: list = [session_id]
        
        if before:
            conditions.append("created_at < ?")
            params.append(before)
        if after:
            conditions.append("created_at > ?")
            params.append(after)
        
        where_clause = "WHERE " + " AND ".join(conditions)
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        cur = self._conn.cursor()
        cur.execute(f"""
            SELECT id, session_id, role, content, tool_calls, tool_call_id, metadata, created_at
            FROM {self.messages_table}
            {where_clause}
            ORDER BY created_at ASC
            {limit_clause}
        """, params)
        
        return [
            ConversationMessage(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                tool_calls=json.loads(row[4]) if row[4] else None,
                tool_call_id=row[5],
                metadata=json.loads(row[6]) if row[6] else None,
                created_at=row[7],
            )
            for row in cur.fetchall()
        ]
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        cur = self._conn.cursor()
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
        self._conn.commit()
        self._sync()
        return deleted
    
    def close(self) -> None:
        """Close the store and release resources."""
        if self._conn:
            self._conn.close()
            self._conn = None
