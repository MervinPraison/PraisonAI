"""
Base template for SQL conversation stores.

Provides a shared implementation that eliminates schema drift, duplicated retry logic,
and copy-pasted CRUD operations across SQL conversation store backends.
"""

import json
import logging
import time as _time
from abc import abstractmethod
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from .base import ConversationStore, ConversationSession, ConversationMessage, validate_identifier

logger = logging.getLogger(__name__)


class _SQLConversationStoreBase(ConversationStore):
    """
    Template base class for SQL conversation stores.
    
    Provides unified schema, retry logic, and CRUD operations.
    Subclasses provide only dialect-specific hooks.
    """
    
    SCHEMA_VERSION = "1.0.0"
    
    # =========================================================================
    # Dialect Hooks (subclass overrides)
    # =========================================================================
    
    _id_type: str = "VARCHAR(255)"
    _json_type: str = "JSONB"
    _float_type: str = "DOUBLE PRECISION"
    _param: str = "%s"   # postgres/mysql=%s; sqlite=?
    _serverless_hosts: tuple = ()
    
    @abstractmethod
    def _connect(self) -> Any:
        """Establish database connection. Return connection object."""
        raise NotImplementedError
    
    @abstractmethod
    def _get_conn(self) -> Any:
        """Get a connection from pool or create new one."""
        raise NotImplementedError
    
    @abstractmethod
    def _put_conn(self, conn: Any, close: bool = False) -> None:
        """Return connection to pool or close it.
        
        Args:
            conn: Connection to return or close
            close: If True, close connection instead of returning to pool
        """
        raise NotImplementedError
    
    @abstractmethod
    def _execute(self, conn: Any, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement. Return result for SELECT, affected rows for DML."""
        raise NotImplementedError
    
    @abstractmethod
    def _fetchone(self, conn: Any, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute SELECT and return one row as dict or None."""
        raise NotImplementedError
    
    @abstractmethod
    def _fetchall(self, conn: Any, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute SELECT and return all rows as list of dicts."""
        raise NotImplementedError
    
    @property
    def _transient_errors(self) -> tuple:
        """Tuple of exception types that indicate transient connection errors."""
        return ()
    
    # =========================================================================
    # Single Source of Truth for Schema
    # =========================================================================
    
    @property
    def _sessions_ddl(self) -> str:
        """DDL for sessions table."""
        return f"""
            CREATE TABLE IF NOT EXISTS {self.sessions_table} (
                session_id  {self._id_type} PRIMARY KEY,
                user_id     {self._id_type},
                agent_id    {self._id_type},
                name        {self._id_type},
                state       {self._json_type},
                metadata    {self._json_type},
                created_at  {self._float_type},
                updated_at  {self._float_type}
            )
        """
    
    @property
    def _messages_ddl(self) -> str:
        """DDL for messages table."""
        return f"""
            CREATE TABLE IF NOT EXISTS {self.messages_table} (
                id          {self._id_type} PRIMARY KEY,
                session_id  {self._id_type} REFERENCES {self.sessions_table}(session_id) ON DELETE CASCADE,
                role        VARCHAR(50),
                content     TEXT,
                tool_calls  {self._json_type},
                tool_call_id {self._id_type},
                metadata    {self._json_type},
                created_at  {self._float_type}
            )
        """
    
    @property
    def _session_indexes(self) -> List[str]:
        """Index definitions for sessions table."""
        return [
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_user "
            f"ON {self.sessions_table}(user_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_agent "
            f"ON {self.sessions_table}(agent_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}sessions_updated "
            f"ON {self.sessions_table}(updated_at DESC)",
        ]
    
    @property 
    def _message_indexes(self) -> List[str]:
        """Index definitions for messages table."""
        return [
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_session "
            f"ON {self.messages_table}(session_id)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}messages_created "
            f"ON {self.messages_table}(created_at DESC)",
        ]
    
    def _decode_json_value(self, value: Any) -> Any:
        """Decode JSON value, handling both string and already-decoded objects."""
        if value is None:
            return None
        return json.loads(value) if isinstance(value, str) else value

    # =========================================================================
    # Initialization
    # =========================================================================
    
    @property
    def sessions_table(self) -> str:
        """Get sessions table name with prefix."""
        return f"{self.table_prefix}sessions"
    
    @property 
    def messages_table(self) -> str:
        """Get messages table name with prefix."""
        return f"{self.table_prefix}messages"

    def __init__(
        self,
        table_prefix: str = "praison_",
        auto_create_tables: bool = True,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        **kwargs
    ):
        """
        Initialize SQL conversation store.
        
        Args:
            table_prefix: Prefix for table names
            auto_create_tables: Create tables if they don't exist
            max_retries: Max retries on connection error (serverless cold-start)
            retry_delay: Base delay between retries in seconds
            **kwargs: Additional arguments passed to subclass
        """
        validate_identifier(table_prefix, "table_prefix")
        self.table_prefix = table_prefix
        
        # Serverless retry configuration
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._serverless = self._detect_serverless(**kwargs)
        
        # Initialize connection
        self._connect()
        
        if auto_create_tables:
            self._create_tables()
    
    def _detect_serverless(self, **kwargs) -> bool:
        """Detect if we're connecting to a serverless database."""
        url = kwargs.get('url', '')
        if not url:
            return False
        
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ''
            return any(hostname.endswith(host) for host in self._serverless_hosts)
        except Exception:
            return False
    
    # =========================================================================
    # Shared Retry Policy
    # =========================================================================
    
    def _execute_with_retry(self, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with retry logic for serverless cold-start."""
        if not self._serverless or not self._transient_errors:
            return operation(*args, **kwargs)
        
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return operation(*args, **kwargs)
            except self._transient_errors as e:
                last_error = e
                logger.warning(
                    f"Connection error (attempt {attempt + 1}/{self._max_retries}): {e}"
                )
                if attempt < self._max_retries - 1:
                    _time.sleep(self._retry_delay * (2 ** attempt))
            except Exception:
                # Non-retryable error, re-raise immediately
                raise
        raise last_error
    
    # =========================================================================
    # Schema Management
    # =========================================================================
    
    def _create_tables(self) -> None:
        """Create tables and indexes if they don't exist."""
        def create_schema(conn):
            # Create tables
            self._execute(conn, self._sessions_ddl)
            self._execute(conn, self._messages_ddl)
            
            # Create indexes
            for index_sql in self._session_indexes + self._message_indexes:
                self._execute(conn, index_sql)
        
        self._execute_with_retry(self._run_with_conn, create_schema)
    
    def _run_with_conn(self, operation: Callable) -> Any:
        """Run operation with connection management."""
        conn = self._get_conn()
        conn_broken = False
        try:
            result = operation(conn)
            # Commit if the connection supports it
            if hasattr(conn, 'commit'):
                conn.commit()
            return result
        except self._transient_errors:
            # Mark connection as broken for transient errors
            conn_broken = True
            raise
        except Exception:
            # Rollback if the connection supports it
            if hasattr(conn, 'rollback'):
                conn.rollback()
            raise
        finally:
            self._put_conn(conn, close=conn_broken)
    
    # =========================================================================
    # Session Operations
    # =========================================================================
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        def insert_session(conn):
            sql = f"""
                INSERT INTO {self.sessions_table} 
                (session_id, user_id, agent_id, name, state, metadata, created_at, updated_at)
                VALUES ({self._param}, {self._param}, {self._param}, {self._param}, 
                        {self._param}, {self._param}, {self._param}, {self._param})
            """
            params = (
                session.session_id,
                session.user_id,
                session.agent_id, 
                session.name,
                json.dumps(session.state) if session.state is not None else None,
                json.dumps(session.metadata) if session.metadata is not None else None,
                session.created_at,
                session.updated_at
            )
            self._execute(conn, sql, params)
        
        self._execute_with_retry(self._run_with_conn, insert_session)
        return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        def fetch_session(conn):
            sql = f"SELECT * FROM {self.sessions_table} WHERE session_id = {self._param}"
            return self._fetchone(conn, sql, (session_id,))
        
        row = self._execute_with_retry(self._run_with_conn, fetch_session)
        if row:
            return ConversationSession(
                session_id=row['session_id'],
                user_id=row['user_id'],
                agent_id=row['agent_id'],
                name=row['name'],
                state=self._decode_json_value(row['state']),
                metadata=self._decode_json_value(row['metadata']),
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
        return None
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        def update_session_row(conn):
            session.updated_at = _time.time()
            sql = f"""
                UPDATE {self.sessions_table} 
                SET user_id = {self._param}, agent_id = {self._param}, name = {self._param},
                    state = {self._param}, metadata = {self._param}, updated_at = {self._param}
                WHERE session_id = {self._param}
            """
            params = (
                session.user_id,
                session.agent_id,
                session.name,
                json.dumps(session.state) if session.state is not None else None,
                json.dumps(session.metadata) if session.metadata is not None else None,
                session.updated_at,
                session.session_id
            )
            self._execute(conn, sql, params)
        
        self._execute_with_retry(self._run_with_conn, update_session_row)
        return session
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        def delete_session_row(conn):
            sql = f"DELETE FROM {self.sessions_table} WHERE session_id = {self._param}"
            return self._execute(conn, sql, (session_id,))
        
        result = self._execute_with_retry(self._run_with_conn, delete_session_row)
        # Different databases return different formats for affected row count
        return bool(result and (result > 0 if isinstance(result, int) else True))
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """List sessions, optionally filtered by user or agent."""
        def fetch_sessions(conn):
            conditions = []
            params = []
            
            # Validate and add pagination params
            safe_limit = int(limit)
            safe_offset = int(offset) 
            if safe_limit < 0 or safe_offset < 0:
                raise ValueError("limit and offset must be non-negative")
            
            if user_id:
                conditions.append(f"user_id = {self._param}")
                params.append(user_id)
            if agent_id:
                conditions.append(f"agent_id = {self._param}")
                params.append(agent_id)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            sql = f"""
                SELECT * FROM {self.sessions_table} 
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT {self._param} OFFSET {self._param}
            """
            return self._fetchall(conn, sql, tuple(params + [safe_limit, safe_offset]))
        
        rows = self._execute_with_retry(self._run_with_conn, fetch_sessions)
        return [
            ConversationSession(
                session_id=row['session_id'],
                user_id=row['user_id'],
                agent_id=row['agent_id'],
                name=row['name'],
                state=self._decode_json_value(row['state']),
                metadata=self._decode_json_value(row['metadata']),
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            for row in rows
        ]
    
    # =========================================================================
    # Message Operations
    # =========================================================================
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a session."""
        def insert_message(conn):
            message.session_id = session_id
            sql = f"""
                INSERT INTO {self.messages_table}
                (id, session_id, role, content, tool_calls, tool_call_id, metadata, created_at)
                VALUES ({self._param}, {self._param}, {self._param}, {self._param}, 
                        {self._param}, {self._param}, {self._param}, {self._param})
            """
            params = (
                message.id,
                message.session_id,
                message.role,
                message.content,
                json.dumps(message.tool_calls) if message.tool_calls is not None else None,
                message.tool_call_id,
                json.dumps(message.metadata) if message.metadata is not None else None,
                message.created_at
            )
            self._execute(conn, sql, params)
        
        self._execute_with_retry(self._run_with_conn, insert_message)
        return message
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Get messages from a session."""
        def fetch_messages(conn):
            conditions = [f"session_id = {self._param}"]
            params = [session_id]
            
            if before is not None:
                conditions.append(f"created_at < {self._param}")
                params.append(before)
            if after is not None:
                conditions.append(f"created_at > {self._param}")
                params.append(after)
            
            where_clause = " WHERE " + " AND ".join(conditions)
            if limit is not None:
                safe_limit = int(limit)
                if safe_limit < 0:
                    raise ValueError("limit must be non-negative")
                limit_clause = f" LIMIT {self._param}"
                params.append(safe_limit)
            else:
                limit_clause = ""
            
            sql = f"""
                SELECT * FROM {self.messages_table}
                {where_clause}
                ORDER BY created_at ASC
                {limit_clause}
            """
            return self._fetchall(conn, sql, tuple(params))
        
        rows = self._execute_with_retry(self._run_with_conn, fetch_messages)
        return [
            ConversationMessage(
                id=row['id'],
                session_id=row['session_id'],
                role=row['role'],
                content=row['content'],
                tool_calls=self._decode_json_value(row['tool_calls']),
                tool_call_id=row['tool_call_id'],
                metadata=self._decode_json_value(row['metadata']),
                created_at=row['created_at']
            )
            for row in rows
        ]
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages. If message_ids is None, delete all messages in session."""
        def delete_message_rows(conn):
            if message_ids is None:
                sql = f"DELETE FROM {self.messages_table} WHERE session_id = {self._param}"
                params = (session_id,)
            else:
                if not message_ids:
                    return 0
                placeholders = ", ".join([self._param] * len(message_ids))
                sql = f"""
                    DELETE FROM {self.messages_table} 
                    WHERE session_id = {self._param} AND id IN ({placeholders})
                """
                params = (session_id, *message_ids)
            
            return self._execute(conn, sql, params)
        
        result = self._execute_with_retry(self._run_with_conn, delete_message_rows)
        return result if isinstance(result, int) else 0