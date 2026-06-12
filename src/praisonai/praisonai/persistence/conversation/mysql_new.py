"""
MySQL implementation using the SQL base template.

Requires: mysql-connector-python or pymysql
Install: pip install mysql-connector-python
"""

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ._sql_base import _SQLConversationStoreBase
from .base import validate_identifier

logger = logging.getLogger(__name__)


class MySQLConversationStore(_SQLConversationStoreBase):
    """
    MySQL-based conversation store using the unified SQL template.
    
    Example:
        store = MySQLConversationStore(
            url="mysql://user:password@localhost:3306/praisonai"
        )
    """
    
    # Dialect-specific settings  
    _json_type = "JSON"
    _float_type = "DOUBLE"
    _param = "%s"
    _serverless_hosts = (".psdb.cloud",)  # PlanetScale gets retry for free
    
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
        pool_size: int = 5,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ):
        """
        Initialize MySQL conversation store.
        
        Args:
            url: Full connection URL (overrides individual params)
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            table_prefix: Prefix for table names
            auto_create_tables: Create tables if they don't exist
            pool_size: Connection pool size
            max_retries: Max retries on connection error (serverless cold-start)
            retry_delay: Base delay between retries in seconds
        """
        try:
            import mysql.connector
            from mysql.connector import pooling
        except ImportError:
            raise ImportError(
                "mysql-connector-python is required for MySQL support. "
                "Install with: pip install mysql-connector-python"
            )
        
        self._mysql = mysql.connector
        self.pool_size = pool_size
        
        # Store connection parameters
        self.url = url
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        
        # Parse URL if provided
        if url:
            parsed = urlparse(url)
            self.host = parsed.hostname or host
            self.port = parsed.port or port
            self.database = parsed.path.lstrip("/") or database
            self.user = parsed.username or user
            self.password = parsed.password or password
        
        # Initialize via parent (handles table creation)
        super().__init__(
            table_prefix=table_prefix,
            auto_create_tables=auto_create_tables,
            max_retries=max_retries,
            retry_delay=retry_delay,
            url=url
        )
        
        if self._serverless:
            logger.info("Serverless MySQL detected — retry enabled")
    
    @property
    def _transient_errors(self) -> tuple:
        """MySQL connection errors that should trigger retry."""
        return (self._mysql.errors.OperationalError, self._mysql.errors.InterfaceError)
    
    def _connect(self) -> Any:
        """Establish MySQL connection pool."""
        from mysql.connector import pooling
        
        self._pool = pooling.MySQLConnectionPool(
            pool_name="praison_mysql_pool",
            pool_size=self.pool_size,
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
        )
        return self._pool
    
    def _get_conn(self) -> Any:
        """Get a connection from the pool."""
        return self._pool.get_connection()
    
    def _put_conn(self, conn: Any, close: bool = False) -> None:
        """Return a connection to the pool."""
        conn.close()
    
    def _execute(self, conn: Any, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement."""
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if sql.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                return cur.rowcount
            return None
    
    def _fetchone(self, conn: Any, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute SELECT and return one row as dict."""
        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    
    def _fetchall(self, conn: Any, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute SELECT and return all rows as list of dicts."""
        with conn.cursor(dictionary=True) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    
    def close(self) -> None:
        """Close the connection pool."""
        # MySQL connection pools don't need explicit closing
        pass