"""
Async MySQL implementation of ConversationStore.

Requires: aiomysql
Install: pip install aiomysql
"""

import asyncio
import json
import logging
import time
from typing import List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class AsyncMySQLConversationStore(ConversationStore):
    """
    Async MySQL conversation store using aiomysql.
    
    Provides high-performance async database operations.
    
    Example:
        store = AsyncMySQLConversationStore(
            host="localhost",
            user="root",
            password="password",
            database="praisonai"
        )
        await store.init()
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 3306,
        database: str = "praisonai",
        user: str = "root",
        password: str = "",
        table_prefix: str = "praisonai_",
        pool_size: int = 10,
    ):
        """
        Initialize async MySQL store.
        
        Args:
            url: MySQL connection URL (takes precedence)
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            table_prefix: Prefix for table names
            pool_size: Connection pool size
        """
        self.url = url
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table_prefix = table_prefix
        self.pool_size = pool_size
        self._pool = None
        self._initialized = False
        
        if url:
            self._parse_url(url)
    
    def _parse_url(self, url: str):
        """Parse MySQL URL into components."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 3306
        self.database = parsed.path.lstrip('/') or "praisonai"
        self.user = parsed.username or "root"
        self.password = parsed.password or ""
    
    async def init(self):
        """Initialize connection pool and create tables."""
        if self._initialized:
            return
        
        try:
            import aiomysql
        except ImportError:
            raise ImportError(
                "aiomysql is required for async MySQL support. "
                "Install with: pip install aiomysql"
            )
        
        self._pool = await aiomysql.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.database,
            minsize=1,
            maxsize=self.pool_size,
            autocommit=True
        )
        
        await self._create_tables()
        self._initialized = True
    
    async def _create_tables(self):
        """Create required tables if they don't exist."""
        sessions_table = f"{self.table_prefix}sessions"
        messages_table = f"{self.table_prefix}messages"
        
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {sessions_table} (
                        session_id VARCHAR(255) PRIMARY KEY,
                        user_id VARCHAR(255),
                        agent_id VARCHAR(255),
                        name VARCHAR(255),
                        metadata JSON,
                        created_at DOUBLE,
                        updated_at DOUBLE,
                        INDEX idx_user_id (user_id),
                        INDEX idx_agent_id (agent_id)
                    )
                """)
                
                await cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {messages_table} (
                        id VARCHAR(255) PRIMARY KEY,
                        session_id VARCHAR(255),
                        role VARCHAR(50),
                        content TEXT,
                        metadata JSON,
                        created_at DOUBLE,
                        INDEX idx_session_id (session_id),
                        FOREIGN KEY (session_id) REFERENCES {sessions_table}(session_id) ON DELETE CASCADE
                    )
                """)
    
    async def async_create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}sessions"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    INSERT INTO {table} (session_id, user_id, agent_id, name, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (session.session_id, session.user_id, session.agent_id, session.name,
                      json.dumps(session.metadata) if session.metadata else None,
                      session.created_at, session.updated_at))
        
        return session
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Sync wrapper for create_session."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_create_session(session)
        )
    
    async def async_get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}sessions"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    SELECT session_id, user_id, agent_id, name, metadata, created_at, updated_at
                    FROM {table} WHERE session_id = %s
                """, (session_id,))
                row = await cur.fetchone()
        
        if row:
            return ConversationSession(
                session_id=row[0],
                user_id=row[1],
                agent_id=row[2],
                name=row[3],
                metadata=json.loads(row[4]) if row[4] else None,
                created_at=row[5],
                updated_at=row[6]
            )
        return None
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Sync wrapper for get_session."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_get_session(session_id)
        )
    
    async def async_update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session asynchronously."""
        if not self._initialized:
            await self.init()
        
        session.updated_at = time.time()
        table = f"{self.table_prefix}sessions"
        
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    UPDATE {table} 
                    SET name = %s, metadata = %s, updated_at = %s
                    WHERE session_id = %s
                """, (session.name, json.dumps(session.metadata) if session.metadata else None,
                      session.updated_at, session.session_id))
        
        return session
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Sync wrapper for update_session."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_update_session(session)
        )
    
    async def async_delete_session(self, session_id: str) -> bool:
        """Delete a session asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}sessions"
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    DELETE FROM {table} WHERE session_id = %s
                """, (session_id,))
                return cur.rowcount > 0
    
    def delete_session(self, session_id: str) -> bool:
        """Sync wrapper for delete_session."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_delete_session(session_id)
        )
    
    async def async_list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """List sessions asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}sessions"
        conditions = []
        params = []
        
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        
        if agent_id:
            conditions.append("agent_id = %s")
            params.append(agent_id)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    SELECT session_id, user_id, agent_id, name, metadata, created_at, updated_at
                    FROM {table} {where_clause}
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                """, params)
                rows = await cur.fetchall()
        
        return [
            ConversationSession(
                session_id=row[0],
                user_id=row[1],
                agent_id=row[2],
                name=row[3],
                metadata=json.loads(row[4]) if row[4] else None,
                created_at=row[5],
                updated_at=row[6]
            )
            for row in rows
        ]
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """Sync wrapper for list_sessions."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_list_sessions(user_id, agent_id, limit, offset)
        )
    
    async def async_add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message asynchronously."""
        if not self._initialized:
            await self.init()
        
        message.session_id = session_id
        table = f"{self.table_prefix}messages"
        
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    INSERT INTO {table} (id, session_id, role, content, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (message.id, session_id, message.role, message.content,
                      json.dumps(message.metadata) if message.metadata else None,
                      message.created_at))
        
        return message
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Sync wrapper for add_message."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_add_message(session_id, message)
        )
    
    async def async_get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Get messages asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}messages"
        conditions = ["session_id = %s"]
        params = [session_id]
        
        if before:
            conditions.append("created_at < %s")
            params.append(before)
        
        if after:
            conditions.append("created_at > %s")
            params.append(after)
        
        where_clause = f"WHERE {' AND '.join(conditions)}"
        limit_clause = "LIMIT %s" if limit else ""
        if limit:
            params.append(limit)
        
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"""
                    SELECT id, session_id, role, content, metadata, created_at
                    FROM {table} {where_clause}
                    ORDER BY created_at ASC {limit_clause}
                """, params)
                rows = await cur.fetchall()
        
        return [
            ConversationMessage(
                id=row[0],
                session_id=row[1],
                role=row[2],
                content=row[3],
                metadata=json.loads(row[4]) if row[4] else None,
                created_at=row[5]
            )
            for row in rows
        ]
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Sync wrapper for get_messages."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_get_messages(session_id, limit, before, after)
        )
    
    async def async_delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}messages"
        
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                if message_ids is None:
                    await cur.execute(f"""
                        DELETE FROM {table} WHERE session_id = %s
                    """, (session_id,))
                else:
                    placeholders = ','.join(['%s'] * len(message_ids))
                    await cur.execute(f"""
                        DELETE FROM {table} WHERE session_id = %s AND id IN ({placeholders})
                    """, [session_id] + message_ids)
                return cur.rowcount
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Sync wrapper for delete_messages."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_delete_messages(session_id, message_ids)
        )
    
    async def async_close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            self._initialized = False
    
    def close(self) -> None:
        """Sync wrapper for close."""
        if self._pool:
            asyncio.get_event_loop().run_until_complete(self.async_close())
