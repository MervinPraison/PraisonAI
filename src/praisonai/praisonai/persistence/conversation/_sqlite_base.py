"""
Shared base for synchronous SQLite ConversationStore backends.

Owns the single source of truth for the SQLite table schema and CRUD logic so
that the two synchronous SQLite stores (shared-connection vs per-call-locking)
do not drift. Subclasses provide only their connection-acquisition strategy and
a few small behavioural hooks.

This mirrors the ``_sql_base.py`` pattern used by the Postgres/MySQL stores but
stays SQLite-specific (``sqlite3`` parameter style, DDL types, row factory).
"""

import json
import logging
import sqlite3
import time as _time
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)


class _SQLiteConversationStoreBase(ConversationStore):
    """
    Template base class for synchronous SQLite conversation stores.

    Provides the shared schema (DDL) and CRUD operations. Subclasses implement
    the ``_connection`` context manager to supply a connection according to their
    connection-management strategy and may override the small behavioural hooks
    documented below.
    """

    SCHEMA_VERSION = "1.0.0"

    # -------------------------------------------------------------------------
    # Behavioural hooks (subclasses may override)
    # -------------------------------------------------------------------------

    #: When True, ``update_session`` refreshes ``updated_at`` to the current time
    #: before writing. The shared-connection store keeps the caller-provided
    #: timestamp (False); the per-call-locking store refreshes it (True).
    _refresh_updated_at_on_update: bool = False

    @property
    def sessions_table(self) -> str:
        return f"{self.table_prefix}sessions"

    @property
    def messages_table(self) -> str:
        return f"{self.table_prefix}messages"

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection for a single logical operation.

        Subclasses must implement this. Implementations are responsible for
        committing (the base commits via ``conn.commit()`` for write paths) and
        for releasing/closing the connection as appropriate to their strategy.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------------
    # Schema (single source of truth)
    # -------------------------------------------------------------------------

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """Create tables and indexes if they don't exist."""
        cur = conn.cursor()

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
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                metadata TEXT,
                created_at REAL,
                FOREIGN KEY (session_id) REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE
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

        cur.execute("PRAGMA foreign_keys = ON")
        conn.commit()
        logger.info(f"SQLite tables created: {self.sessions_table}, {self.messages_table}")

    # -------------------------------------------------------------------------
    # Row marshalling
    # -------------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: Any) -> ConversationSession:
        return ConversationSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            name=row["name"],
            state=json.loads(row["state"]) if row["state"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_message(row: Any) -> ConversationMessage:
        return ConversationMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            tool_calls=json.loads(row["tool_calls"]) if row["tool_calls"] else None,
            tool_call_id=row["tool_call_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else None,
            created_at=row["created_at"],
        )

    # -------------------------------------------------------------------------
    # Session operations
    # -------------------------------------------------------------------------

    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        with self._connection() as conn:
            conn.execute(f"""
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
            conn.commit()
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        with self._connection() as conn:
            cur = conn.execute(
                f"SELECT * FROM {self.sessions_table} WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return self._row_to_session(row)

    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        if self._refresh_updated_at_on_update:
            session.updated_at = _time.time()
        with self._connection() as conn:
            conn.execute(f"""
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
            conn.commit()
        return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        with self._connection() as conn:
            conn.execute(
                f"DELETE FROM {self.messages_table} WHERE session_id = ?",
                (session_id,),
            )
            cur = conn.execute(
                f"DELETE FROM {self.sessions_table} WHERE session_id = ?",
                (session_id,),
            )
            deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: Optional[int] = 100,
        offset: Optional[int] = 0,
    ) -> List[ConversationSession]:
        """List sessions, optionally filtered by user or agent."""
        conditions: List[str] = []
        params: List[Any] = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if agent_id:
            conditions.append("agent_id = ?")
            params.append(agent_id)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # SQLite requires a LIMIT when OFFSET is used; use -1 (unbounded) when
        # an offset is supplied without an explicit limit.
        if limit is not None:
            params.append(limit)
            limit_clause = " LIMIT ?"
        elif offset is not None:
            params.append(-1)
            limit_clause = " LIMIT ?"
        else:
            limit_clause = ""

        if offset is not None:
            params.append(offset)
            offset_clause = " OFFSET ?"
        else:
            offset_clause = ""

        with self._connection() as conn:
            cur = conn.execute(
                f"SELECT * FROM {self.sessions_table}{where_clause}"
                f" ORDER BY updated_at DESC{limit_clause}{offset_clause}",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_session(row) for row in rows]

    # -------------------------------------------------------------------------
    # Message operations
    # -------------------------------------------------------------------------

    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a session."""
        actual_session_id = session_id or message.session_id
        message.session_id = actual_session_id
        with self._connection() as conn:
            conn.execute(f"""
                INSERT INTO {self.messages_table}
                (id, session_id, role, content, tool_calls, tool_call_id, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message.id,
                actual_session_id,
                message.role,
                message.content,
                json.dumps(message.tool_calls) if message.tool_calls else None,
                message.tool_call_id,
                json.dumps(message.metadata) if message.metadata else None,
                message.created_at,
            ))
            conn.commit()
        return message

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None,
        offset: Optional[int] = None,
    ) -> List[ConversationMessage]:
        """Get messages from a session."""
        conditions = ["session_id = ?"]
        params: List[Any] = [session_id]

        if before is not None:
            conditions.append("created_at < ?")
            params.append(before)
        if after is not None:
            conditions.append("created_at > ?")
            params.append(after)

        where_clause = " WHERE " + " AND ".join(conditions)

        if limit is not None:
            params.append(limit)
            limit_clause = " LIMIT ?"
        elif offset is not None:
            params.append(-1)
            limit_clause = " LIMIT ?"
        else:
            limit_clause = ""

        if offset is not None:
            params.append(offset)
            offset_clause = " OFFSET ?"
        else:
            offset_clause = ""

        with self._connection() as conn:
            cur = conn.execute(
                f"SELECT * FROM {self.messages_table}{where_clause}"
                f" ORDER BY created_at ASC{limit_clause}{offset_clause}",
                params,
            )
            rows = cur.fetchall()
        return [self._row_to_message(row) for row in rows]

    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages. If message_ids is None, delete all messages in session."""
        with self._connection() as conn:
            if message_ids:
                placeholders = ",".join(["?"] * len(message_ids))
                cur = conn.execute(
                    f"DELETE FROM {self.messages_table}"
                    f" WHERE session_id = ? AND id IN ({placeholders})",
                    [session_id] + message_ids,
                )
            else:
                cur = conn.execute(
                    f"DELETE FROM {self.messages_table} WHERE session_id = ?",
                    (session_id,),
                )
            deleted = cur.rowcount
            conn.commit()
        return deleted
