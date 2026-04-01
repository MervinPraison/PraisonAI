"""
PostgreSQL Storage Adapter for PraisonAI Agents.

Provides PostgreSQL-based storage backend implementing StorageBackendProtocol.
Uses lazy imports for the psycopg2 dependency to avoid module-level import overhead.

Example:
    ```python
    from praisonaiagents.storage import PostgreSQLStorageAdapter
    
    # Basic usage with defaults
    adapter = PostgreSQLStorageAdapter()
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    
    # Custom PostgreSQL configuration
    adapter = PostgreSQLStorageAdapter(
        host="localhost",
        port=5432,
        database="myapp",
        user="postgres",
        password="secret",
        table_name="praisonai_storage"
    )
    ```
"""

import json
import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class PostgreSQLStorageAdapter:
    """
    PostgreSQL-based storage backend implementing StorageBackendProtocol.
    
    Stores data as JSON in a PostgreSQL table with JSONB support for efficient querying.
    Thread-safe with connection pooling.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: Optional[str] = None,
        table_name: str = "praisonai_storage",
        connect_timeout: int = 10,
        **kwargs
    ):
        """
        Initialize PostgreSQL storage adapter.
        
        Args:
            host: PostgreSQL host address
            port: PostgreSQL port number
            database: Database name
            user: Username for authentication
            password: Password for authentication
            table_name: Table name for storing data
            connect_timeout: Connection timeout in seconds
            **kwargs: Additional psycopg2 connection parameters
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table_name = table_name
        self.connect_timeout = connect_timeout
        self.connection_kwargs = kwargs
        self._connection_pool = None
        self._lock = threading.Lock()
    
    def _get_connection(self):
        """Get PostgreSQL connection with lazy initialization and pooling."""
        if self._connection_pool is None:
            with self._lock:
                if self._connection_pool is None:
                    try:
                        import psycopg2
                        from psycopg2 import pool, sql
                        self._psycopg2 = psycopg2
                        self._sql = sql
                    except ImportError:
                        raise ImportError(
                            "psycopg2 not installed. Install with: pip install praisonaiagents[postgresql]"
                        )
                    
                    # Create connection pool
                    try:
                        self._connection_pool = pool.SimpleConnectionPool(
                            minconn=1,
                            maxconn=10,
                            host=self.host,
                            port=self.port,
                            database=self.database,
                            user=self.user,
                            password=self.password,
                            connect_timeout=self.connect_timeout,
                            **self.connection_kwargs
                        )
                        
                        # Create table if it doesn't exist
                        self._ensure_table()
                        
                    except Exception as e:
                        self._connection_pool = None
                        raise ConnectionError(f"Failed to connect to PostgreSQL: {e}")
        
        return self._connection_pool.getconn()
    
    def _return_connection(self, conn):
        """Return connection to pool."""
        if self._connection_pool:
            self._connection_pool.putconn(conn)
    
    def _ensure_table(self):
        """Create storage table if it doesn't exist."""
        conn = None
        try:
            conn = self._connection_pool.getconn()
            with conn.cursor() as cursor:
                create_table_sql = self._sql.SQL("""
                    CREATE TABLE IF NOT EXISTS {} (
                        key VARCHAR(255) PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """).format(self._sql.Identifier(self.table_name))
                
                cursor.execute(create_table_sql)
                
                # Create index on JSONB data for performance
                index_sql = self._sql.SQL("""
                    CREATE INDEX IF NOT EXISTS {} ON {} USING GIN (data)
                """).format(
                    self._sql.Identifier(f"{self.table_name}_data_gin_idx"),
                    self._sql.Identifier(self.table_name)
                )
                cursor.execute(index_sql)
                
                conn.commit()
                logger.debug(f"Ensured PostgreSQL table exists: {self.table_name}")
                
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to create PostgreSQL table: {e}")
            raise
        finally:
            if conn:
                self._connection_pool.putconn(conn)
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """
        Save data to PostgreSQL.
        
        Args:
            key: Unique identifier for the data
            data: Dictionary to save
            
        Raises:
            ConnectionError: If PostgreSQL is unavailable
            ValueError: If data cannot be serialized
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                upsert_sql = self._sql.SQL("""
                    INSERT INTO {} (key, data, updated_at) 
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) 
                    DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
                """).format(self._sql.Identifier(self.table_name))
                
                cursor.execute(upsert_sql, (key, json.dumps(data)))
                conn.commit()
                logger.debug(f"Saved data to PostgreSQL key: {key}")
                
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to save data to PostgreSQL key {key}: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)
    
    def load(self, key: str) -> Any:
        """
        Load data from PostgreSQL.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            The stored data, or None if not found
            
        Raises:
            ConnectionError: If PostgreSQL is unavailable
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                select_sql = self._sql.SQL("""
                    SELECT data FROM {} WHERE key = %s
                """).format(self._sql.Identifier(self.table_name))
                
                cursor.execute(select_sql, (key,))
                row = cursor.fetchone()
                
                if row is None:
                    logger.debug(f"No data found for PostgreSQL key: {key}")
                    return None
                
                data = row[0]  # JSONB is automatically parsed by psycopg2
                logger.debug(f"Loaded data from PostgreSQL key: {key}")
                return data
                
        except Exception as e:
            logger.error(f"Failed to load data from PostgreSQL key {key}: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)
    
    def delete(self, key: str) -> bool:
        """
        Delete data from PostgreSQL.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ConnectionError: If PostgreSQL is unavailable
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                delete_sql = self._sql.SQL("""
                    DELETE FROM {} WHERE key = %s
                """).format(self._sql.Identifier(self.table_name))
                
                cursor.execute(delete_sql, (key,))
                conn.commit()
                
                success = cursor.rowcount > 0
                if success:
                    logger.debug(f"Deleted PostgreSQL key: {key}")
                else:
                    logger.debug(f"PostgreSQL key not found for deletion: {key}")
                return success
                
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to delete PostgreSQL key {key}: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """
        List all keys, optionally filtered by prefix.
        
        Args:
            prefix: Optional prefix to filter keys
            
        Returns:
            List of matching keys
            
        Raises:
            ConnectionError: If PostgreSQL is unavailable
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                if prefix:
                    select_sql = self._sql.SQL("""
                        SELECT key FROM {} WHERE key LIKE %s ORDER BY key
                    """).format(self._sql.Identifier(self.table_name))
                    cursor.execute(select_sql, (f"{prefix}%",))
                else:
                    select_sql = self._sql.SQL("""
                        SELECT key FROM {} ORDER BY key
                    """).format(self._sql.Identifier(self.table_name))
                    cursor.execute(select_sql)
                
                keys = [row[0] for row in cursor.fetchall()]
                logger.debug(f"Found {len(keys)} keys matching prefix: {prefix}")
                return keys
                
        except Exception as e:
            logger.error(f"Failed to list PostgreSQL keys with prefix {prefix}: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in PostgreSQL.
        
        Args:
            key: Unique identifier to check
            
        Returns:
            True if exists, False otherwise
            
        Raises:
            ConnectionError: If PostgreSQL is unavailable
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                exists_sql = self._sql.SQL("""
                    SELECT 1 FROM {} WHERE key = %s LIMIT 1
                """).format(self._sql.Identifier(self.table_name))
                
                cursor.execute(exists_sql, (key,))
                exists = cursor.fetchone() is not None
                logger.debug(f"PostgreSQL key {'exists' if exists else 'does not exist'}: {key}")
                return exists
                
        except Exception as e:
            logger.error(f"Failed to check existence of PostgreSQL key {key}: {e}")
            raise
        finally:
            if conn:
                self._return_connection(conn)
    
    def close(self) -> None:
        """Close PostgreSQL connection pool if open."""
        if self._connection_pool is not None:
            try:
                self._connection_pool.closeall()
                logger.debug("Closed PostgreSQL connection pool")
            except Exception as e:
                logger.warning(f"Error closing PostgreSQL connection pool: {e}")
            finally:
                self._connection_pool = None


__all__ = ["PostgreSQLStorageAdapter"]