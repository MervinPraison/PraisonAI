"""
Supabase implementation of ConversationStore.

Requires: supabase
Install: pip install supabase
"""

import logging
import time
from typing import List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage, validate_identifier

logger = logging.getLogger(__name__)


class SupabaseConversationStore(ConversationStore):
    """
    Supabase-based conversation store.
    
    Uses Supabase's PostgreSQL backend via REST API.
    
    Example:
        store = SupabaseConversationStore(
            url="https://xxx.supabase.co",
            key="your-anon-key"
        )
    """
    
    SCHEMA_VERSION = "1.0.0"
    
    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
        table_prefix: str = "praison_",
        auto_create_tables: bool = False,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        """
        Initialize Supabase conversation store.
        
        Args:
            url: Supabase project URL
            key: Supabase anon/service key
            table_prefix: Prefix for table names
            auto_create_tables: Create tables via Supabase SQL (requires service key)
            max_retries: Max retries for paused project wake-up
            retry_delay: Base delay between retries in seconds
        """
        validate_identifier(table_prefix, "table_prefix")
        try:
            from supabase import create_client, Client
        except ImportError:
            raise ImportError(
                "supabase is required for Supabase support. "
                "Install with: pip install supabase"
            )
        
        import os
        url = url or os.getenv("SUPABASE_URL")
        key = key or os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            raise ValueError("Supabase URL and key are required")
        
        self._client: Client = create_client(url, key)
        self.table_prefix = table_prefix
        self.sessions_table = f"{table_prefix}sessions"
        self.messages_table = f"{table_prefix}messages"
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        
        if auto_create_tables:
            self._create_tables()
    
    def _execute_with_retry(self, operation, *args, **kwargs):
        """Execute a Supabase operation with retry for paused project wake-up."""
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if any(kw in error_str for kw in ("connection", "timeout", "503", "502", "unavailable")):
                    logger.warning(
                        f"Supabase connection error (attempt {attempt + 1}/{self._max_retries}): {e}"
                    )
                    if attempt < self._max_retries - 1:
                        time.sleep(self._retry_delay * (2 ** attempt))
                    continue
                raise
        raise last_error
    
    def _create_tables(self) -> None:
        """Create tables via Supabase SQL RPC (requires service key)."""
        sessions_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.sessions_table} (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                agent_id TEXT,
                name TEXT,
                state JSONB,
                metadata JSONB,
                created_at DOUBLE PRECISION,
                updated_at DOUBLE PRECISION
            );
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_user 
            ON {self.sessions_table}(user_id);
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_agent 
            ON {self.sessions_table}(agent_id);
        """
        messages_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.messages_table} (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL
                    REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT,
                tool_calls JSONB,
                tool_call_id TEXT,
                metadata JSONB,
                created_at DOUBLE PRECISION
            );
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_session 
            ON {self.messages_table}(session_id);
            CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_created 
            ON {self.messages_table}(session_id, created_at);
        """
        try:
            self._client.rpc("exec_sql", {"query": sessions_sql}).execute()
            self._client.rpc("exec_sql", {"query": messages_sql}).execute()
            logger.info(f"Supabase tables created: {self.sessions_table}, {self.messages_table}")
        except Exception as e:
            logger.warning(
                f"Could not auto-create tables via RPC: {e}. "
                f"Create tables manually via Supabase dashboard or SQL editor."
            )
    
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
        self._client.table(self.sessions_table).insert(data).execute()
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        result = self._client.table(self.sessions_table).select("*").eq("session_id", session_id).execute()
        if not result.data:
            return None
        row = result.data[0]
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
        data = {
            "user_id": session.user_id,
            "agent_id": session.agent_id,
            "name": session.name,
            "state": session.state,
            "metadata": session.metadata,
            "updated_at": session.updated_at,
        }
        self._client.table(self.sessions_table).update(data).eq("session_id", session.session_id).execute()
        return session
    
    def delete_session(self, session_id: str) -> bool:
        # Delete messages first
        self._client.table(self.messages_table).delete().eq("session_id", session_id).execute()
        result = self._client.table(self.sessions_table).delete().eq("session_id", session_id).execute()
        return len(result.data) > 0 if result.data else False
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        query = self._client.table(self.sessions_table).select("*")
        if user_id:
            query = query.eq("user_id", user_id)
        if agent_id:
            query = query.eq("agent_id", agent_id)
        query = query.order("updated_at", desc=True).range(offset, offset + limit - 1)
        result = query.execute()
        
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
            for row in (result.data or [])
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
        self._client.table(self.messages_table).insert(data).execute()
        return message
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        query = self._client.table(self.messages_table).select("*").eq("session_id", session_id)
        if before:
            query = query.lt("created_at", before)
        if after:
            query = query.gt("created_at", after)
        query = query.order("created_at", desc=False)
        if limit:
            query = query.limit(limit)
        result = query.execute()
        
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
            for row in (result.data or [])
        ]
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        if message_ids:
            result = self._client.table(self.messages_table).delete().eq("session_id", session_id).in_("id", message_ids).execute()
        else:
            result = self._client.table(self.messages_table).delete().eq("session_id", session_id).execute()
        return len(result.data) if result.data else 0
    
    def close(self) -> None:
        pass  # Supabase client doesn't need explicit close
