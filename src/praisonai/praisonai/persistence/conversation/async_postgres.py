"""
Async PostgreSQL implementation of ConversationStore.

Requires: asyncpg
Install: pip install asyncpg
"""

import asyncio
import json
import logging
import time
from typing import List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class AsyncPostgresConversationStore(ConversationStore):
    """
    Async PostgreSQL conversation store using asyncpg.
    
    Provides high-performance async database operations.
    
    Example:
        store = AsyncPostgresConversationStore(
            url="postgresql://user:pass@localhost:5432/praisonai"
        )
        await store.init()
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: str = "",
        table_prefix: str = "praisonai_",
        pool_size: int = 10,
    ):
        """
        Initialize async PostgreSQL store.
        
        Args:
            url: PostgreSQL connection URL (takes precedence)
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
    
    async def init(self):
        """Initialize connection pool and create tables."""
        if self._initialized:
            return
        
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                "asyncpg is required for async PostgreSQL support. "
                "Install with: pip install asyncpg"
            )
        
        if self.url:
            self._pool = await asyncpg.create_pool(self.url, min_size=1, max_size=self.pool_size)
        else:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=1,
                max_size=self.pool_size
            )
        
        await self._create_tables()
        self._initialized = True
    
    async def _create_tables(self):
        """Create required tables if they don't exist."""
        sessions_table = f"{self.table_prefix}sessions"
        messages_table = f"{self.table_prefix}messages"
        
        async with self._pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {sessions_table} (
                    session_id VARCHAR(255) PRIMARY KEY,
                    user_id VARCHAR(255),
                    agent_id VARCHAR(255),
                    name VARCHAR(255),
                    metadata JSONB,
                    created_at DOUBLE PRECISION,
                    updated_at DOUBLE PRECISION
                )
            """)
            
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {messages_table} (
                    id VARCHAR(255) PRIMARY KEY,
                    session_id VARCHAR(255) REFERENCES {sessions_table}(session_id) ON DELETE CASCADE,
                    role VARCHAR(50),
                    content TEXT,
                    metadata JSONB,
                    created_at DOUBLE PRECISION
                )
            """)
            
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{messages_table}_session 
                ON {messages_table}(session_id)
            """)
    
    async def async_create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}sessions"
        async with self._pool.acquire() as conn:
            await conn.execute(f"""
                INSERT INTO {table} (session_id, user_id, agent_id, name, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, session.session_id, session.user_id, session.agent_id, session.name,
                json.dumps(session.metadata) if session.metadata else None,
                session.created_at, session.updated_at)
        
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
            row = await conn.fetchrow(f"""
                SELECT * FROM {table} WHERE session_id = $1
            """, session_id)
        
        if row:
            return ConversationSession(
                session_id=row['session_id'],
                user_id=row['user_id'],
                agent_id=row['agent_id'],
                name=row['name'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
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
            await conn.execute(f"""
                UPDATE {table} 
                SET name = $2, metadata = $3, updated_at = $4
                WHERE session_id = $1
            """, session.session_id, session.name,
                json.dumps(session.metadata) if session.metadata else None,
                session.updated_at)
        
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
            result = await conn.execute(f"""
                DELETE FROM {table} WHERE session_id = $1
            """, session_id)
        
        return "DELETE 1" in result
    
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
        param_idx = 1
        
        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1
        
        if agent_id:
            conditions.append(f"agent_id = ${param_idx}")
            params.append(agent_id)
            param_idx += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT * FROM {table} {where_clause}
                ORDER BY updated_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
            """, *params)
        
        return [
            ConversationSession(
                session_id=row['session_id'],
                user_id=row['user_id'],
                agent_id=row['agent_id'],
                name=row['name'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at'],
                updated_at=row['updated_at']
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
            await conn.execute(f"""
                INSERT INTO {table} (id, session_id, role, content, metadata, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, message.id, session_id, message.role, message.content,
                json.dumps(message.metadata) if message.metadata else None,
                message.created_at)
        
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
        conditions = ["session_id = $1"]
        params = [session_id]
        param_idx = 2
        
        if before:
            conditions.append(f"created_at < ${param_idx}")
            params.append(before)
            param_idx += 1
        
        if after:
            conditions.append(f"created_at > ${param_idx}")
            params.append(after)
            param_idx += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}"
        limit_clause = f"LIMIT ${param_idx}" if limit else ""
        if limit:
            params.append(limit)
        
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT * FROM {table} {where_clause}
                ORDER BY created_at ASC {limit_clause}
            """, *params)
        
        return [
            ConversationMessage(
                id=row['id'],
                session_id=row['session_id'],
                role=row['role'],
                content=row['content'],
                metadata=json.loads(row['metadata']) if row['metadata'] else None,
                created_at=row['created_at']
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
            if message_ids is None:
                result = await conn.execute(f"""
                    DELETE FROM {table} WHERE session_id = $1
                """, session_id)
            else:
                result = await conn.execute(f"""
                    DELETE FROM {table} WHERE session_id = $1 AND id = ANY($2)
                """, session_id, message_ids)
        
        # Parse count from result like "DELETE 5"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Sync wrapper for delete_messages."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_delete_messages(session_id, message_ids)
        )
    
    async def async_close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self._initialized = False
    
    def close(self) -> None:
        """Sync wrapper for close."""
        if self._pool:
            asyncio.get_event_loop().run_until_complete(self.async_close())
