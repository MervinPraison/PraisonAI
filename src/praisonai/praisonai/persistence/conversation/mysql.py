"""
MySQL implementation of ConversationStore.

Requires: mysql-connector-python or pymysql
Install: pip install mysql-connector-python
"""

import json
import logging
from typing import Any, List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class MySQLConversationStore(ConversationStore):
    """
    MySQL-based conversation store.
    
    Example:
        store = MySQLConversationStore(
            url="mysql://user:password@localhost:3306/praisonai"
        )
    """
    
    SCHEMA_VERSION = "1.0.0"
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 3306,
        database: str = "praisonai",
        user: str = "root",
        password: str = "",
        table_prefix: str = "praison_",
        auto_create_tables: bool = True,
        pool_size: int = 5,
    ):
        """
        Initialize MySQL conversation store.
        
        Args:
            url: Full connection URL (overrides individual params)
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            table_prefix: Prefix for table names
            auto_create_tables: Create tables if they don't exist
            pool_size: Connection pool size
        """
        try:
            import mysql.connector
            from mysql.connector import pooling
        except ImportError:
            raise ImportError(
                "mysql-connector-python is required for MySQL support. "
                "Install with: pip install mysql-connector-python"
            )
        
        self._mysql = mysql.connector
        self.table_prefix = table_prefix
        self.sessions_table = f"{table_prefix}sessions"
        self.messages_table = f"{table_prefix}messages"
        
        # Parse URL if provided
        if url:
            # Parse mysql://user:pass@host:port/database
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or host
            port = parsed.port or port
            database = parsed.path.lstrip("/") or database
            user = parsed.username or user
            password = parsed.password or password
        
        # Create connection pool
        self._pool = pooling.MySQLConnectionPool(
            pool_name="praison_mysql_pool",
            pool_size=pool_size,
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
        )
        
        if auto_create_tables:
            self._create_tables()
    
    def _get_conn(self):
        """Get a connection from the pool."""
        return self._pool.get_connection()
    
    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            # Sessions table
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.sessions_table} (
                    session_id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255),
                    agent_id VARCHAR(255),
                    name VARCHAR(255),
                    state JSON,
                    metadata JSON,
                    created_at DOUBLE,
                    updated_at DOUBLE,
                    INDEX idx_user (user_id),
                    INDEX idx_agent (agent_id),
                    INDEX idx_updated (updated_at DESC)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            # Messages table
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.messages_table} (
                    id VARCHAR(255) PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    content TEXT,
                    tool_calls JSON,
                    tool_call_id VARCHAR(255),
                    metadata JSON,
                    created_at DOUBLE,
                    INDEX idx_session (session_id),
                    INDEX idx_created (session_id, created_at),
                    FOREIGN KEY (session_id) REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            
            conn.commit()
            logger.info(f"MySQL tables created: {self.sessions_table}, {self.messages_table}")
        finally:
            cur.close()
            conn.close()
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                INSERT INTO {self.sessions_table} 
                (session_id, user_id, agent_id, name, state, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        finally:
            cur.close()
            conn.close()
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        conn = self._get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(f"""
                SELECT * FROM {self.sessions_table} WHERE session_id = %s
            """, (session_id,))
            row = cur.fetchone()
            if not row:
                return None
            return ConversationSession(
                session_id=row["session_id"],
                user_id=row["user_id"],
                agent_id=row["agent_id"],
                name=row["name"],
                state=row["state"] if isinstance(row["state"], dict) else (json.loads(row["state"]) if row["state"] else None),
                metadata=row["metadata"] if isinstance(row["metadata"], dict) else (json.loads(row["metadata"]) if row["metadata"] else None),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        finally:
            cur.close()
            conn.close()
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                UPDATE {self.sessions_table}
                SET user_id = %s, agent_id = %s, name = %s, 
                    state = %s, metadata = %s, updated_at = %s
                WHERE session_id = %s
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
        finally:
            cur.close()
            conn.close()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                DELETE FROM {self.sessions_table} WHERE session_id = %s
            """, (session_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        finally:
            cur.close()
            conn.close()
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """List sessions."""
        conn = self._get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            
            conditions = []
            params: List[Any] = []
            
            if user_id:
                conditions.append("user_id = %s")
                params.append(user_id)
            if agent_id:
                conditions.append("agent_id = %s")
                params.append(agent_id)
            
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            params.extend([limit, offset])
            
            cur.execute(f"""
                SELECT * FROM {self.sessions_table}
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
            """, params)
            
            return [
                ConversationSession(
                    session_id=row["session_id"],
                    user_id=row["user_id"],
                    agent_id=row["agent_id"],
                    name=row["name"],
                    state=row["state"] if isinstance(row["state"], dict) else (json.loads(row["state"]) if row["state"] else None),
                    metadata=row["metadata"] if isinstance(row["metadata"], dict) else (json.loads(row["metadata"]) if row["metadata"] else None),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in cur.fetchall()
            ]
        finally:
            cur.close()
            conn.close()
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a session."""
        message.session_id = session_id
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                INSERT INTO {self.messages_table}
                (id, session_id, role, content, tool_calls, tool_call_id, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        finally:
            cur.close()
            conn.close()
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Get messages from a session."""
        conn = self._get_conn()
        try:
            cur = conn.cursor(dictionary=True)
            
            conditions = ["session_id = %s"]
            params: List[Any] = [session_id]
            
            if before:
                conditions.append("created_at < %s")
                params.append(before)
            if after:
                conditions.append("created_at > %s")
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
                    tool_calls=row["tool_calls"] if isinstance(row["tool_calls"], list) else (json.loads(row["tool_calls"]) if row["tool_calls"] else None),
                    tool_call_id=row["tool_call_id"],
                    metadata=row["metadata"] if isinstance(row["metadata"], dict) else (json.loads(row["metadata"]) if row["metadata"] else None),
                    created_at=row["created_at"],
                )
                for row in cur.fetchall()
            ]
        finally:
            cur.close()
            conn.close()
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages."""
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            
            if message_ids:
                placeholders = ",".join(["%s"] * len(message_ids))
                cur.execute(f"""
                    DELETE FROM {self.messages_table}
                    WHERE session_id = %s AND id IN ({placeholders})
                """, [session_id] + message_ids)
            else:
                cur.execute(f"""
                    DELETE FROM {self.messages_table} WHERE session_id = %s
                """, (session_id,))
            
            deleted = cur.rowcount
            conn.commit()
            return deleted
        finally:
            cur.close()
            conn.close()
    
    def close(self) -> None:
        """Close the store."""
        pass  # Pool handles cleanup
