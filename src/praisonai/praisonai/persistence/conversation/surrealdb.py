"""
SurrealDB implementation of ConversationStore.

Requires: surrealdb
Install: pip install surrealdb
"""

import json
import logging
from typing import List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class SurrealDBConversationStore(ConversationStore):
    """
    SurrealDB-based conversation store.
    
    SurrealDB is a multi-model database supporting SQL-like queries.
    
    Example:
        store = SurrealDBConversationStore(
            url="ws://localhost:8000/rpc",
            namespace="praisonai",
            database="conversations"
        )
    """
    
    SCHEMA_VERSION = "1.0.0"
    
    def __init__(
        self,
        url: str = "ws://localhost:8000/rpc",
        namespace: str = "praisonai",
        database: str = "conversations",
        username: Optional[str] = None,
        password: Optional[str] = None,
        table_prefix: str = "praison_",
        auto_create_tables: bool = True,
    ):
        try:
            from surrealdb import Surreal
        except ImportError:
            raise ImportError(
                "surrealdb is required for SurrealDB support. "
                "Install with: pip install surrealdb"
            )
        
        self._Surreal = Surreal
        self.url = url
        self.namespace = namespace
        self.database = database
        self.username = username
        self.password = password
        self.table_prefix = table_prefix
        self.sessions_table = f"{table_prefix}sessions"
        self.messages_table = f"{table_prefix}messages"
        self._client = None
        
        # Note: SurrealDB Python client is async, we'll use sync wrapper
        self._init_sync()
    
    def _init_sync(self):
        """Initialize synchronously using asyncio."""
        import asyncio
        
        async def _init():
            self._client = self._Surreal(self.url)
            await self._client.connect()
            if self.username and self.password:
                await self._client.signin({"user": self.username, "pass": self.password})
            await self._client.use(self.namespace, self.database)
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(_init())
    
    def _run_sync(self, coro):
        """Run async coroutine synchronously."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        data = {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "agent_id": session.agent_id,
            "name": session.name,
            "state": session.state,
            "metadata": session.metadata,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }
        self._run_sync(self._client.create(self.sessions_table, data))
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        result = self._run_sync(
            self._client.query(
                f"SELECT * FROM {self.sessions_table} WHERE session_id = $sid",
                {"sid": session_id}
            )
        )
        if not result or not result[0].get("result"):
            return None
        row = result[0]["result"][0]
        return ConversationSession(
            session_id=row["session_id"],
            user_id=row.get("user_id"),
            agent_id=row.get("agent_id"),
            name=row.get("name"),
            state=row.get("state"),
            metadata=row.get("metadata"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        self._run_sync(
            self._client.query(
                f"""UPDATE {self.sessions_table} SET 
                    user_id = $user_id, agent_id = $agent_id, name = $name,
                    state = $state, metadata = $metadata, updated_at = $updated_at
                    WHERE session_id = $session_id""",
                {
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "agent_id": session.agent_id,
                    "name": session.name,
                    "state": session.state,
                    "metadata": session.metadata,
                    "updated_at": session.updated_at,
                }
            )
        )
        return session
    
    def delete_session(self, session_id: str) -> bool:
        self._run_sync(
            self._client.query(
                f"DELETE FROM {self.messages_table} WHERE session_id = $sid",
                {"sid": session_id}
            )
        )
        result = self._run_sync(
            self._client.query(
                f"DELETE FROM {self.sessions_table} WHERE session_id = $sid",
                {"sid": session_id}
            )
        )
        return True
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        conditions = []
        params = {"limit": limit, "offset": offset}
        
        if user_id:
            conditions.append("user_id = $user_id")
            params["user_id"] = user_id
        if agent_id:
            conditions.append("agent_id = $agent_id")
            params["agent_id"] = agent_id
        
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        result = self._run_sync(
            self._client.query(
                f"SELECT * FROM {self.sessions_table} {where} ORDER BY updated_at DESC LIMIT $limit START $offset",
                params
            )
        )
        
        if not result or not result[0].get("result"):
            return []
        
        return [
            ConversationSession(
                session_id=row["session_id"],
                user_id=row.get("user_id"),
                agent_id=row.get("agent_id"),
                name=row.get("name"),
                state=row.get("state"),
                metadata=row.get("metadata"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
            for row in result[0]["result"]
        ]
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        message.session_id = session_id
        data = {
            "id": message.id,
            "session_id": session_id,
            "role": message.role,
            "content": message.content,
            "tool_calls": message.tool_calls,
            "tool_call_id": message.tool_call_id,
            "metadata": message.metadata,
            "created_at": message.created_at,
        }
        self._run_sync(self._client.create(self.messages_table, data))
        return message
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        conditions = ["session_id = $session_id"]
        params = {"session_id": session_id}
        
        if before:
            conditions.append("created_at < $before")
            params["before"] = before
        if after:
            conditions.append("created_at > $after")
            params["after"] = after
        
        where = "WHERE " + " AND ".join(conditions)
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        result = self._run_sync(
            self._client.query(
                f"SELECT * FROM {self.messages_table} {where} ORDER BY created_at ASC {limit_clause}",
                params
            )
        )
        
        if not result or not result[0].get("result"):
            return []
        
        return [
            ConversationMessage(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row.get("content", ""),
                tool_calls=row.get("tool_calls"),
                tool_call_id=row.get("tool_call_id"),
                metadata=row.get("metadata"),
                created_at=row.get("created_at"),
            )
            for row in result[0]["result"]
        ]
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        if message_ids:
            self._run_sync(
                self._client.query(
                    f"DELETE FROM {self.messages_table} WHERE session_id = $sid AND id IN $ids",
                    {"sid": session_id, "ids": message_ids}
                )
            )
            return len(message_ids)
        else:
            self._run_sync(
                self._client.query(
                    f"DELETE FROM {self.messages_table} WHERE session_id = $sid",
                    {"sid": session_id}
                )
            )
            return -1
    
    def close(self) -> None:
        if self._client:
            self._run_sync(self._client.close())
            self._client = None
