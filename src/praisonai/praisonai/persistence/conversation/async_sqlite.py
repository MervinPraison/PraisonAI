"""
Async SQLite implementation of ConversationStore.

Requires: aiosqlite
Install: pip install aiosqlite
"""

import asyncio
import json
import logging
import time
from typing import List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class AsyncSQLiteConversationStore(ConversationStore):
    """
    Async SQLite conversation store using aiosqlite.
    
    Provides async database operations for SQLite.
    
    Example:
        store = AsyncSQLiteConversationStore(path="./conversations.db")
        await store.init()
    """
    
    def __init__(
        self,
        path: str = "praisonai_conversations.db",
        table_prefix: str = "praisonai_",
    ):
        """
        Initialize async SQLite store.
        
        Args:
            path: Path to SQLite database file
            table_prefix: Prefix for table names
        """
        self.path = path
        self.table_prefix = table_prefix
        self._conn = None
        self._initialized = False
    
    async def init(self):
        """Initialize connection and create tables."""
        if self._initialized:
            return
        
        try:
            import aiosqlite
        except ImportError:
            raise ImportError(
                "aiosqlite is required for async SQLite support. "
                "Install with: pip install aiosqlite"
            )
        
        self._aiosqlite = aiosqlite
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._create_tables()
        self._initialized = True
    
    async def _create_tables(self):
        """Create required tables if they don't exist."""
        sessions_table = f"{self.table_prefix}sessions"
        messages_table = f"{self.table_prefix}messages"
        
        await self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {sessions_table} (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                agent_id TEXT,
                name TEXT,
                metadata TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)
        
        await self._conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {messages_table} (
                id TEXT PRIMARY KEY,
                session_id TEXT REFERENCES {sessions_table}(session_id) ON DELETE CASCADE,
                role TEXT,
                content TEXT,
                metadata TEXT,
                created_at REAL
            )
        """)
        
        await self._conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{messages_table}_session 
            ON {messages_table}(session_id)
        """)
        
        await self._conn.commit()
    
    async def async_create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session asynchronously."""
        if not self._initialized:
            await self.init()
        
        table = f"{self.table_prefix}sessions"
        await self._conn.execute(f"""
            INSERT INTO {table} (session_id, user_id, agent_id, name, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session.session_id, session.user_id, session.agent_id, session.name,
              json.dumps(session.metadata) if session.metadata else None,
              session.created_at, session.updated_at))
        await self._conn.commit()
        
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
        async with self._conn.execute(f"""
            SELECT * FROM {table} WHERE session_id = ?
        """, (session_id,)) as cursor:
            row = await cursor.fetchone()
        
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
        
        await self._conn.execute(f"""
            UPDATE {table} 
            SET name = ?, metadata = ?, updated_at = ?
            WHERE session_id = ?
        """, (session.name, json.dumps(session.metadata) if session.metadata else None,
              session.updated_at, session.session_id))
        await self._conn.commit()
        
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
        cursor = await self._conn.execute(f"""
            DELETE FROM {table} WHERE session_id = ?
        """, (session_id,))
        await self._conn.commit()
        
        return cursor.rowcount > 0
    
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
            conditions.append("user_id = ?")
            params.append(user_id)
        
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.extend([limit, offset])
        
        async with self._conn.execute(f"""
            SELECT * FROM {table} {where_clause}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
        """, params) as cursor:
            rows = await cursor.fetchall()
        
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
        
        await self._conn.execute(f"""
            INSERT INTO {table} (id, session_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (message.id, session_id, message.role, message.content,
              json.dumps(message.metadata) if message.metadata else None,
              message.created_at))
        await self._conn.commit()
        
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
        conditions = ["session_id = ?"]
        params = [session_id]
        
        if before:
            conditions.append("created_at < ?")
            params.append(before)
        
        if after:
            conditions.append("created_at > ?")
            params.append(after)
        
        where_clause = f"WHERE {' AND '.join(conditions)}"
        limit_clause = f"LIMIT ?" if limit else ""
        if limit:
            params.append(limit)
        
        async with self._conn.execute(f"""
            SELECT * FROM {table} {where_clause}
            ORDER BY created_at ASC {limit_clause}
        """, params) as cursor:
            rows = await cursor.fetchall()
        
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
        
        if message_ids is None:
            cursor = await self._conn.execute(f"""
                DELETE FROM {table} WHERE session_id = ?
            """, (session_id,))
        else:
            placeholders = ','.join(['?' for _ in message_ids])
            cursor = await self._conn.execute(f"""
                DELETE FROM {table} WHERE session_id = ? AND id IN ({placeholders})
            """, [session_id] + message_ids)
        
        await self._conn.commit()
        return cursor.rowcount
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Sync wrapper for delete_messages."""
        return asyncio.get_event_loop().run_until_complete(
            self.async_delete_messages(session_id, message_ids)
        )
    
    async def async_close(self) -> None:
        """Close the connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._initialized = False
    
    def close(self) -> None:
        """Sync wrapper for close."""
        if self._conn:
            asyncio.get_event_loop().run_until_complete(self.async_close())
