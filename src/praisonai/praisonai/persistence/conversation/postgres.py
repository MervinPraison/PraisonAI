"""
PostgreSQL implementation of ConversationStore.

Requires: psycopg2-binary or psycopg2
Install: pip install psycopg2-binary
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class PostgresConversationStore(ConversationStore):
    """
    PostgreSQL-based conversation store.
    
    Connection URL format: postgresql://user:password@host:port/database
    
    Example:
        store = PostgresConversationStore(
            url="postgresql://postgres:password@localhost:5432/praisonai"
        )
    """
    
    SCHEMA_VERSION = "1.0.0"
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: str = "",
        schema: str = "public",
        table_prefix: str = "praison_",
        auto_create_tables: bool = True,
        pool_size: int = 5,
    ):
        """
        Initialize PostgreSQL conversation store.
        
        Args:
            url: Full connection URL (overrides individual params)
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            schema: PostgreSQL schema
            table_prefix: Prefix for table names
            auto_create_tables: Create tables if they don't exist
            pool_size: Connection pool size
        """
        try:
            import psycopg2
            from psycopg2 import pool as pg_pool
            from psycopg2.extras import RealDictCursor
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgreSQL support. "
                "Install with: pip install psycopg2-binary"
            )
        
        self._psycopg2 = psycopg2
        self._RealDictCursor = RealDictCursor
        
        self.schema = schema
        self.table_prefix = table_prefix
        self.sessions_table = f"{schema}.{table_prefix}sessions"
        self.messages_table = f"{schema}.{table_prefix}messages"
        
        # Build connection params
        if url:
            self._pool = pg_pool.ThreadedConnectionPool(1, pool_size, url)
        else:
            self._pool = pg_pool.ThreadedConnectionPool(
                1, pool_size,
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
        return self._pool.getconn()
    
    def _put_conn(self, conn):
        """Return a connection to the pool."""
        self._pool.putconn(conn)
    
    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # Create schema if not exists
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
                
                # Sessions table
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.sessions_table} (
                        session_id VARCHAR(255) PRIMARY KEY,
                        user_id VARCHAR(255),
                        agent_id VARCHAR(255),
                        name VARCHAR(255),
                        state JSONB,
                        metadata JSONB,
                        created_at DOUBLE PRECISION,
                        updated_at DOUBLE PRECISION
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
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_updated 
                    ON {self.sessions_table}(updated_at DESC)
                """)
                
                # Messages table
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.messages_table} (
                        id VARCHAR(255) PRIMARY KEY,
                        session_id VARCHAR(255) NOT NULL 
                            REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE,
                        role VARCHAR(50) NOT NULL,
                        content TEXT,
                        tool_calls JSONB,
                        tool_call_id VARCHAR(255),
                        metadata JSONB,
                        created_at DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())
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
                
                conn.commit()
                logger.info(f"PostgreSQL tables created: {self.sessions_table}, {self.messages_table}")
        finally:
            self._put_conn(conn)
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {self.sessions_table} 
                    (session_id, user_id, agent_id, name, state, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING session_id
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
            self._put_conn(conn)
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._RealDictCursor) as cur:
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
                    state=row["state"],
                    metadata=row["metadata"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
        finally:
            self._put_conn(conn)
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
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
            self._put_conn(conn)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    DELETE FROM {self.sessions_table} WHERE session_id = %s
                """, (session_id,))
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
        finally:
            self._put_conn(conn)
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """List sessions, optionally filtered by user or agent."""
        conn = self._get_conn()
        try:
            with conn.cursor(cursor_factory=self._RealDictCursor) as cur:
                conditions = []
                params = []
                
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
                        state=row["state"],
                        metadata=row["metadata"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in cur.fetchall()
                ]
        finally:
            self._put_conn(conn)
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a session."""
        message.session_id = session_id
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
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
            self._put_conn(conn)
    
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
            with conn.cursor(cursor_factory=self._RealDictCursor) as cur:
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
                        tool_calls=row["tool_calls"],
                        tool_call_id=row["tool_call_id"],
                        metadata=row["metadata"],
                        created_at=row["created_at"],
                    )
                    for row in cur.fetchall()
                ]
        finally:
            self._put_conn(conn)
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages. If message_ids is None, delete all messages in session."""
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
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
            self._put_conn(conn)
    
    def close(self) -> None:
        """Close the store and release resources."""
        if self._pool:
            self._pool.closeall()
            self._pool = None
