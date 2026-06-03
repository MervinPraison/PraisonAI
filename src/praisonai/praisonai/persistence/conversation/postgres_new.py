"""
PostgreSQL implementation using the SQL base template.

Requires: psycopg2-binary or psycopg2
Install: pip install psycopg2-binary
"""

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from ._sql_base import _SQLConversationStoreBase
from .base import validate_identifier

logger = logging.getLogger(__name__)


class PostgresConversationStore(_SQLConversationStoreBase):
    """
    PostgreSQL-based conversation store using the unified SQL template.
    
    Connection URL format: postgresql://user:password@host:port/database
    
    Example:
        store = PostgresConversationStore(
            url="postgresql://postgres:password@localhost:5432/praisonai"
        )
    """
    
    # Dialect-specific settings
    _json_type = "JSONB"
    _float_type = "DOUBLE PRECISION" 
    _param = "%s"
    _serverless_hosts = (
        ".neon.tech",
        ".cockroachlabs.cloud", 
        ".cockroachlabs.com",
        ".xata.sh",
        ".supabase.com",
        ".supabase.co",
    )
    
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
        max_retries: int = 3,
        retry_delay: float = 0.5,
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
            max_retries: Max retries on connection error (serverless cold-start)
            retry_delay: Base delay between retries in seconds
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
        
        validate_identifier(schema, "schema")
        self.schema = schema
        self.pool_size = pool_size
        
        # Store connection parameters
        self.url = url
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        
        # Auto-enforce SSL for serverless providers
        if url:
            url = self._ensure_ssl(url)
            self.url = url
        
        # Initialize via parent (handles table creation)
        super().__init__(
            table_prefix=table_prefix,
            auto_create_tables=auto_create_tables, 
            max_retries=max_retries,
            retry_delay=retry_delay,
            url=url
        )
        
        if self._serverless:
            logger.info("Serverless PostgreSQL detected — retry and SSL enabled")
    
    @property
    def _transient_errors(self) -> tuple:
        """PostgreSQL connection errors that should trigger retry.""" 
        return (self._psycopg2.OperationalError,)
    
    @property
    def sessions_table(self) -> str:
        """Override to include schema prefix."""
        return f"{self.schema}.{self.table_prefix}sessions"
        
    @property
    def messages_table(self) -> str:
        """Override to include schema prefix."""
        return f"{self.schema}.{self.table_prefix}messages"
    
    @property
    def _sessions_ddl(self) -> str:
        """Override to create schema first."""
        return f"""
            CREATE SCHEMA IF NOT EXISTS {self.schema};
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
    
    def _connect(self) -> Any:
        """Establish PostgreSQL connection pool."""
        from psycopg2 import pool as pg_pool
        
        connect_timeout = 30 if self._serverless else 5
        
        if self.url:
            # Append connect_timeout for serverless if not already set
            url = self.url
            if self._serverless and "connect_timeout" not in url:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}connect_timeout={connect_timeout}"
            self._pool = pg_pool.ThreadedConnectionPool(1, self.pool_size, url)
        else:
            self._pool = pg_pool.ThreadedConnectionPool(
                1, self.pool_size,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=connect_timeout,
            )
        
        return self._pool
    
    def _get_conn(self) -> Any:
        """Get a connection from the pool."""
        return self._pool.getconn()
    
    def _put_conn(self, conn: Any) -> None:
        """Return a connection to the pool."""
        self._pool.putconn(conn)
    
    def _execute(self, conn: Any, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement."""
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if sql.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                return cur.rowcount
            return None
    
    def _fetchone(self, conn: Any, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute SELECT and return one row as dict."""
        with conn.cursor(cursor_factory=self._RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
    
    def _fetchall(self, conn: Any, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute SELECT and return all rows as list of dicts.""" 
        with conn.cursor(cursor_factory=self._RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    
    def close(self) -> None:
        """Close the connection pool."""
        if hasattr(self, '_pool') and self._pool:
            self._pool.closeall()
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    @staticmethod
    def _is_serverless(url: str) -> bool:
        """Check if URL points to a serverless PostgreSQL provider."""
        if not url:
            return False
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            return any(hostname.endswith(host) for host in PostgresConversationStore._serverless_hosts)
        except Exception:
            return False
    
    @staticmethod
    def _ensure_ssl(url: str) -> str:
        """Ensure SSL is enabled for serverless PostgreSQL connections."""
        if not PostgresConversationStore._is_serverless(url):
            return url
        if "sslmode=" in url.lower():
            return url
        separator = "&" if "?" in url else "?"
        return f"{url}{separator}sslmode=require"