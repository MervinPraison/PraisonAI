"""
PostgreSQL Storage Adapter for PraisonAI Agents.

Provides PostgreSQL-based storage implementation following StorageBackendProtocol.
Uses lazy imports for the optional psycopg2 dependency.

Example:
    ```python
    from praisonaiagents.storage import PostgreSQLStorageAdapter
    
    adapter = PostgreSQLStorageAdapter(
        host="localhost",
        database="praisonai",
        user="postgres",
        password="password"
    )
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    ```
"""

import json
import time
import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class PostgreSQLStorageAdapter:
    """
    PostgreSQL-based storage adapter implementing StorageBackendProtocol.
    
    Uses PostgreSQL for ACID-compliant relational data storage with JSON support.
    Requires the `psycopg2-binary` package (optional dependency).
    Thread-safe with connection pooling.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: str = "",
        table_name: str = "praison_storage",
        schema: str = "public",
        sslmode: str = "prefer",
        max_connections: int = 20,
    ):
        """
        Initialize the PostgreSQL storage adapter.
        
        Args:
            host: PostgreSQL server host
            port: PostgreSQL server port
            database: Database name
            user: Username for authentication
            password: Password for authentication
            table_name: Table name for storage
            schema: Schema name
            sslmode: SSL mode (disable, allow, prefer, require)
            max_connections: Maximum connections in pool
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table_name = table_name
        self.schema = schema
        self.sslmode = sslmode
        self.max_connections = max_connections
        self._pool = None
        self._lock = threading.Lock()
    
    def _get_pool(self):
        """Lazy initialize connection pool."""
        if self._pool is None:
            with self._lock:
                if self._pool is None:  # Double-check locking
                    try:
                        import psycopg2
                        from psycopg2 import pool
                    except ImportError:
                        raise ImportError(
                            "PostgreSQL storage adapter requires the 'psycopg2-binary' package. "
                            "Install with: pip install praisonaiagents[postgresql]"
                        )
                    
                    connection_string = (
                        f"host={self.host} "
                        f"port={self.port} "
                        f"dbname={self.database} "
                        f"user={self.user} "
                        f"password={self.password} "
                        f"sslmode={self.sslmode}"
                    )
                    
                    try:
                        self._pool = pool.ThreadedConnectionPool(
                            minconn=1,
                            maxconn=self.max_connections,
                            dsn=connection_string
                        )
                        logger.info(f"Connected to PostgreSQL at {self.host}:{self.port}")
                        
                        # Create table if it doesn't exist
                        self._create_table()
                    except Exception as e:
                        logger.error(f"Failed to connect to PostgreSQL: {e}")
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
    
    def _create_table(self) -> None:
        """Create storage table if it doesn't exist."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Create table with JSONB for better performance
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema}.{self.table_name} (
                    key VARCHAR(255) PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated_at 
                ON {self.schema}.{self.table_name}(updated_at)
            """)
            
            # Create GIN index for JSONB queries (optional but recommended)
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_data_gin 
                ON {self.schema}.{self.table_name} USING gin(data)
            """)
            
            # Create trigger to update updated_at column
            cursor.execute(f"""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql'
            """)
            
            cursor.execute(f"""
                DROP TRIGGER IF EXISTS update_{self.table_name}_updated_at 
                ON {self.schema}.{self.table_name}
            """)
            
            cursor.execute(f"""
                CREATE TRIGGER update_{self.table_name}_updated_at 
                BEFORE UPDATE ON {self.schema}.{self.table_name}
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
            """)
            
            conn.commit()
            logger.debug(f"Created PostgreSQL table: {self.schema}.{self.table_name}")
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to create PostgreSQL table: {e}")
            raise
        finally:
            if conn:
                self._put_connection(conn)
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Use JSONB for better performance and native JSON operations
            cursor.execute(f"""
                INSERT INTO {self.schema}.{self.table_name} (key, data)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET
                    data = EXCLUDED.data,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, json.dumps(data, default=str)))
            
            conn.commit()
            logger.debug(f"Saved data to PostgreSQL key: {key}")
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to save data to PostgreSQL key {key}: {e}")
            raise
        finally:
            if conn:
                self._put_connection(conn)
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT data FROM {self.schema}.{self.table_name} WHERE key = %s
            """, (key,))
            
            row = cursor.fetchone()
            if row:
                # Data is already parsed as dict due to JSONB
                return row[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to load data from PostgreSQL key {key}: {e}")
            return None
        finally:
            if conn:
                self._put_connection(conn)
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                DELETE FROM {self.schema}.{self.table_name} WHERE key = %s
            """, (key,))
            
            deleted = cursor.rowcount > 0
            conn.commit()
            
            if deleted:
                logger.debug(f"Deleted PostgreSQL key: {key}")
            
            return deleted
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to delete PostgreSQL key {key}: {e}")
            return False
        finally:
            if conn:
                self._put_connection(conn)
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if prefix:
                cursor.execute(f"""
                    SELECT key FROM {self.schema}.{self.table_name}
                    WHERE key LIKE %s
                    ORDER BY key
                """, (f"{prefix}%",))
            else:
                cursor.execute(f"""
                    SELECT key FROM {self.schema}.{self.table_name}
                    ORDER BY key
                """)
            
            return [row[0] for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Failed to list PostgreSQL keys: {e}")
            return []
        finally:
            if conn:
                self._put_connection(conn)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT 1 FROM {self.schema}.{self.table_name} 
                WHERE key = %s LIMIT 1
            """, (key,))
            
            return cursor.fetchone() is not None
            
        except Exception as e:
            logger.error(f"Failed to check existence of PostgreSQL key {key}: {e}")
            return False
        finally:
            if conn:
                self._put_connection(conn)
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT COUNT(*) FROM {self.schema}.{self.table_name}")
            count = cursor.fetchone()[0]
            
            cursor.execute(f"DELETE FROM {self.schema}.{self.table_name}")
            conn.commit()
            
            logger.info(f"Cleared {count} rows from PostgreSQL")
            return count
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to clear PostgreSQL data: {e}")
            return 0
        finally:
            if conn:
                self._put_connection(conn)
    
    def query_json(self, json_path: str, value: Any) -> List[str]:
        """
        Query keys by JSON path.
        
        Args:
            json_path: JSON path expression (e.g., '$.user.name')
            value: Value to match
            
        Returns:
            List of matching keys
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT key FROM {self.schema}.{self.table_name}
                WHERE data #>> %s = %s
                ORDER BY key
            """, (json_path.replace('$.', '').split('.'), str(value)))
            
            return [row[0] for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Failed to query PostgreSQL JSON data: {e}")
            return []
        finally:
            if conn:
                self._put_connection(conn)
    
    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            try:
                self._pool.closeall()
                logger.debug("Closed PostgreSQL connection pool")
            except Exception as e:
                logger.warning(f"Error closing PostgreSQL pool: {e}")
            finally:
                self._pool = None


__all__ = ['PostgreSQLStorageAdapter']