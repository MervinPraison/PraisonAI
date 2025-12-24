"""
SingleStore implementation of ConversationStore.

Requires: singlestoredb
Install: pip install singlestoredb
"""

import json
import logging
from typing import Any, List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class SingleStoreConversationStore(ConversationStore):
    """
    SingleStore-based conversation store.
    
    SingleStore is MySQL-compatible with additional vector capabilities.
    
    Example:
        store = SingleStoreConversationStore(
            url="singlestoredb://user:password@host:3306/database"
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
    ):
        try:
            import singlestoredb as s2
        except ImportError:
            raise ImportError(
                "singlestoredb is required for SingleStore support. "
                "Install with: pip install singlestoredb"
            )
        
        self._s2 = s2
        self.table_prefix = table_prefix
        self.sessions_table = f"{table_prefix}sessions"
        self.messages_table = f"{table_prefix}messages"
        
        if url:
            self._conn = s2.connect(url)
        else:
            self._conn = s2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
        
        if auto_create_tables:
            self._create_tables()
    
    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        cur = self._conn.cursor()
        
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
                KEY idx_user (user_id),
                KEY idx_agent (agent_id)
            )
        """)
        
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
                KEY idx_session (session_id),
                KEY idx_created (session_id, created_at)
            )
        """)
        
        self._conn.commit()
        logger.info(f"SingleStore tables created")
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        cur = self._conn.cursor()
        cur.execute(f"""
            INSERT INTO {self.sessions_table} 
            (session_id, user_id, agent_id, name, state, metadata, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session.session_id, session.user_id, session.agent_id, session.name,
            json.dumps(session.state) if session.state else None,
            json.dumps(session.metadata) if session.metadata else None,
            session.created_at, session.updated_at,
        ))
        self._conn.commit()
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        cur = self._conn.cursor()
        cur.execute(f"SELECT * FROM {self.sessions_table} WHERE session_id = %s", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        return ConversationSession(
            session_id=data["session_id"], user_id=data["user_id"],
            agent_id=data["agent_id"], name=data["name"],
            state=json.loads(data["state"]) if data["state"] else None,
            metadata=json.loads(data["metadata"]) if data["metadata"] else None,
            created_at=data["created_at"], updated_at=data["updated_at"],
        )
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        cur = self._conn.cursor()
        cur.execute(f"""
            UPDATE {self.sessions_table}
            SET user_id=%s, agent_id=%s, name=%s, state=%s, metadata=%s, updated_at=%s
            WHERE session_id=%s
        """, (
            session.user_id, session.agent_id, session.name,
            json.dumps(session.state) if session.state else None,
            json.dumps(session.metadata) if session.metadata else None,
            session.updated_at, session.session_id,
        ))
        self._conn.commit()
        return session
    
    def delete_session(self, session_id: str) -> bool:
        cur = self._conn.cursor()
        cur.execute(f"DELETE FROM {self.messages_table} WHERE session_id = %s", (session_id,))
        cur.execute(f"DELETE FROM {self.sessions_table} WHERE session_id = %s", (session_id,))
        self._conn.commit()
        return cur.rowcount > 0
    
    def list_sessions(self, user_id: Optional[str] = None, agent_id: Optional[str] = None,
                      limit: int = 100, offset: int = 0) -> List[ConversationSession]:
        cur = self._conn.cursor()
        conditions, params = [], []
        if user_id:
            conditions.append("user_id = %s")
            params.append(user_id)
        if agent_id:
            conditions.append("agent_id = %s")
            params.append(agent_id)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        params.extend([limit, offset])
        cur.execute(f"SELECT * FROM {self.sessions_table} {where} ORDER BY updated_at DESC LIMIT %s OFFSET %s", params)
        cols = [d[0] for d in cur.description]
        return [ConversationSession(
            session_id=dict(zip(cols, r))["session_id"],
            user_id=dict(zip(cols, r))["user_id"],
            agent_id=dict(zip(cols, r))["agent_id"],
            name=dict(zip(cols, r))["name"],
            state=json.loads(dict(zip(cols, r))["state"]) if dict(zip(cols, r))["state"] else None,
            metadata=json.loads(dict(zip(cols, r))["metadata"]) if dict(zip(cols, r))["metadata"] else None,
            created_at=dict(zip(cols, r))["created_at"],
            updated_at=dict(zip(cols, r))["updated_at"],
        ) for r in cur.fetchall()]
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        message.session_id = session_id
        cur = self._conn.cursor()
        cur.execute(f"""
            INSERT INTO {self.messages_table}
            (id, session_id, role, content, tool_calls, tool_call_id, metadata, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            message.id, session_id, message.role, message.content,
            json.dumps(message.tool_calls) if message.tool_calls else None,
            message.tool_call_id,
            json.dumps(message.metadata) if message.metadata else None,
            message.created_at,
        ))
        self._conn.commit()
        return message
    
    def get_messages(self, session_id: str, limit: Optional[int] = None,
                     before: Optional[float] = None, after: Optional[float] = None) -> List[ConversationMessage]:
        cur = self._conn.cursor()
        conditions, params = ["session_id = %s"], [session_id]
        if before:
            conditions.append("created_at < %s")
            params.append(before)
        if after:
            conditions.append("created_at > %s")
            params.append(after)
        where = "WHERE " + " AND ".join(conditions)
        limit_clause = f"LIMIT {limit}" if limit else ""
        cur.execute(f"SELECT * FROM {self.messages_table} {where} ORDER BY created_at ASC {limit_clause}", params)
        cols = [d[0] for d in cur.description]
        return [ConversationMessage(
            id=dict(zip(cols, r))["id"],
            session_id=dict(zip(cols, r))["session_id"],
            role=dict(zip(cols, r))["role"],
            content=dict(zip(cols, r))["content"],
            tool_calls=json.loads(dict(zip(cols, r))["tool_calls"]) if dict(zip(cols, r))["tool_calls"] else None,
            tool_call_id=dict(zip(cols, r))["tool_call_id"],
            metadata=json.loads(dict(zip(cols, r))["metadata"]) if dict(zip(cols, r))["metadata"] else None,
            created_at=dict(zip(cols, r))["created_at"],
        ) for r in cur.fetchall()]
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        cur = self._conn.cursor()
        if message_ids:
            placeholders = ",".join(["%s"] * len(message_ids))
            cur.execute(f"DELETE FROM {self.messages_table} WHERE session_id = %s AND id IN ({placeholders})",
                       [session_id] + message_ids)
        else:
            cur.execute(f"DELETE FROM {self.messages_table} WHERE session_id = %s", (session_id,))
        self._conn.commit()
        return cur.rowcount
    
    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
