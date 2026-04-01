"""
PostgreSQL Storage Adapter for PraisonAI Agents.

Provides PostgreSQLStorageAdapter implementing StorageBackendProtocol:
- ACID-compliant relational storage
- Connection pooling for performance
- JSONB support for efficient JSON operations
- Automatic table creation with proper indexing
- Thread-safe operations

Architecture:
- Uses lazy imports (psycopg2 package is optional)
- Implements StorageBackendProtocol
- Zero performance impact when not used
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class PostgreSQLStorageAdapter:
    """
    PostgreSQL-based storage adapter implementing StorageBackendProtocol.
    
    Uses PostgreSQL for ACID-compliant, scalable relational storage with JSONB support.
    Requires the `psycopg2` package (optional dependency).
    
    Features:
    - Connection pooling for performance
    - JSONB data type for efficient JSON operations
    - Automatic table and index creation
    - GIN indexes for fast prefix searches
    - ACID compliance for data integrity
    - Thread-safe operations
    
    Example:
        ```python
        from praisonaiagents.storage import PostgreSQLStorageAdapter
        
        adapter = PostgreSQLStorageAdapter(
            host="localhost",
            database="praisonai",
            user="user",
            password="password"
        )
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: str = "",
        table_name: str = "praison_storage",
        connection_string: Optional[str] = None,
        min_connections: int = 5,
        max_connections: int = 20,
        auto_create: bool = True,
    ):
        """
        Initialize the PostgreSQL storage adapter.
        
        Args:
            host: PostgreSQL server host
            port: PostgreSQL server port
            database: Database name
            user: Database user
            password: Database password
            table_name: Table name for storage
            connection_string: Full connection string (overrides other params)
            min_connections: Minimum connections in pool
            max_connections: Maximum connections in pool
            auto_create: Create table if it doesn't exist
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table_name = table_name
        self.connection_string = connection_string
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.auto_create = auto_create
        self._pool = None
        self._lock = threading.Lock()
    
    def _get_connection_string(self) -> str:
        """Build connection string if not provided."""
        if self.connection_string:
            return self.connection_string
        
        password_part = f":'{self.password}'" if self.password else ""
        return f"postgresql://{self.user}{password_part}@{self.host}:{self.port}/{self.database}"
    
    def _get_pool(self):
        """Lazy initialize connection pool."""
        if self._pool is None:
            with self._lock:
                if self._pool is None:  # Double-check pattern
                    try:
                        import psycopg2
                        from psycopg2 import pool
                    except ImportError:
                        raise ImportError(
                            "PostgreSQL storage adapter requires the 'psycopg2' package. "
                            "Install with: pip install praisonaiagents[postgresql]"
                        )
                    
                    try:
                        self._pool = pool.ThreadedConnectionPool(
                            self.min_connections,
                            self.max_connections,
                            self._get_connection_string()
                        )
                        
                        logger.info(f"PostgreSQL connection pool created: {self.host}:{self.port}/{self.database}")
                        
                        if self.auto_create:
                            self._create_table()
                            
                    except Exception as e:
                        logger.error(f"Failed to create PostgreSQL connection pool: {e}")
                        raise
        
        return self._pool
    
    def _get_connection(self):
        """Get connection from pool."""
        pool = self._get_pool()
        return pool.getconn()
    
    def _put_connection(self, conn):
        """Return connection to pool."""
        if self._pool:
            self._pool.putconn(conn)
    
    def _create_table(self):
        """Create storage table with proper indexes."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Create table with JSONB for efficient JSON operations
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    key VARCHAR(255) PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create GIN index for fast JSON operations
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_data_gin 
                ON {self.table_name} USING GIN (data)
            """)
            
            # Create index for prefix queries on keys
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_key_prefix 
                ON {self.table_name} (key varchar_pattern_ops)
            """)
            
            # Create index on updated_at for cleanup operations
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated_at 
                ON {self.table_name} (updated_at)
            """)
            
            conn.commit()
            logger.debug(f"Created PostgreSQL table and indexes: {self.table_name}")
            
        except Exception as e:
            logger.error(f"Failed to create PostgreSQL table: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._put_connection(conn)
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Use JSONB for efficient storage and querying
            cur.execute(f"""
                INSERT INTO {self.table_name} (key, data, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET
                    data = EXCLUDED.data,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, json.dumps(data, default=str, ensure_ascii=False)))
            
            conn.commit()
            logger.debug(f"Saved data to PostgreSQL key: {key}")
            
        except Exception as e:
            logger.error(f"Failed to save data to PostgreSQL key '{key}': {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self._put_connection(conn)
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            cur.execute(f"""
                SELECT data FROM {self.table_name} WHERE key = %s
            """, (key,))
            
            result = cur.fetchone()
            if result:
                # PostgreSQL JSONB is automatically parsed
                data = result[0]
                logger.debug(f"Loaded data from PostgreSQL key: {key}")
                return data
            return None
        except Exception as e:
            logger.error(f"Failed to load data from PostgreSQL key '{key}': {e}")
            return None
        finally:
            if conn:
                self._put_connection(conn)
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            cur.execute(f"""
                DELETE FROM {self.table_name} WHERE key = %s
            """, (key,))
            
            deleted = cur.rowcount > 0
            conn.commit()
            
            if deleted:
                logger.debug(f"Deleted PostgreSQL key: {key}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete PostgreSQL key '{key}': {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                self._put_connection(conn)
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            if prefix:
                # Use LIKE with varchar_pattern_ops index for efficient prefix queries
                cur.execute(f"""
                    SELECT key FROM {self.table_name}
                    WHERE key LIKE %s
                    ORDER BY key
                """, (f"{prefix}%",))
            else:
                cur.execute(f"""
                    SELECT key FROM {self.table_name}
                    ORDER BY key
                """)
            
            keys = [row[0] for row in cur.fetchall()]
            logger.debug(f"Listed {len(keys)} PostgreSQL keys with prefix: '{prefix}'")
            return keys
        except Exception as e:
            logger.error(f"Failed to list PostgreSQL keys with prefix '{prefix}': {e}")
            return []
        finally:
            if conn:
                self._put_connection(conn)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            cur.execute(f"""
                SELECT 1 FROM {self.table_name} WHERE key = %s LIMIT 1
            """, (key,))
            
            return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Failed to check if PostgreSQL key '{key}' exists: {e}")
            return False
        finally:
            if conn:
                self._put_connection(conn)
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            count = cur.fetchone()[0]
            
            cur.execute(f"DELETE FROM {self.table_name}")
            conn.commit()
            
            logger.info(f"Cleared {count} PostgreSQL records from table '{self.table_name}'")
            return count
        except Exception as e:
            logger.error(f"Failed to clear PostgreSQL table: {e}")
            if conn:
                conn.rollback()
            return 0
        finally:
            if conn:
                self._put_connection(conn)
    
    def count(self) -> int:
        """Get total number of stored items."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to count PostgreSQL records: {e}")
            return 0
        finally:
            if conn:
                self._put_connection(conn)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get table statistics."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get table size and statistics
            cur.execute(f"""
                SELECT 
                    schemaname,
                    tablename,
                    attname,
                    n_distinct,
                    most_common_vals,
                    most_common_freqs,
                    histogram_bounds
                FROM pg_stats 
                WHERE tablename = %s
            """, (self.table_name,))
            
            stats_rows = cur.fetchall()
            
            # Get table size
            cur.execute(f"""
                SELECT pg_total_relation_size(%s::regclass) as size_bytes
            """, (self.table_name,))
            
            size_result = cur.fetchone()
            size_bytes = size_result[0] if size_result else 0
            
            return {
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "stats": [dict(zip(['schemaname', 'tablename', 'attname', 'n_distinct', 
                                  'most_common_vals', 'most_common_freqs', 'histogram_bounds'], row))
                         for row in stats_rows]
            }
        except Exception as e:
            logger.error(f"Failed to get PostgreSQL table stats: {e}")
            return {}
        finally:
            if conn:
                self._put_connection(conn)
    
    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            try:
                self._pool.closeall()
                logger.info("PostgreSQL connection pool closed")
            except Exception as e:
                logger.error(f"Error closing PostgreSQL connection pool: {e}")
            finally:
                self._pool = None


__all__ = ['PostgreSQLStorageAdapter']