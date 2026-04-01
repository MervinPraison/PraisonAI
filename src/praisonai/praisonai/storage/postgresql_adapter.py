"""
PostgreSQL Storage Adapter for PraisonAI.

Implements StorageBackendProtocol using PostgreSQL for relational storage.
This is the wrapper implementation that contains the heavy PostgreSQL dependency.
"""

import json
import time
import threading
from typing import Dict, Any, List, Optional


class PostgreSQLStorageAdapter:
    """
    PostgreSQL-based storage backend adapter.
    
    Uses PostgreSQL for robust, ACID-compliant data storage.
    Implements StorageBackendProtocol from praisonaiagents.storage.protocols.
    
    Example:
        ```python
        from praisonai.storage import PostgreSQLStorageAdapter
        
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
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: str = "",
        table: str = "praisonai_storage",
        sslmode: str = "prefer",
        connect_timeout: int = 10,
        command_timeout: int = 30,
        max_connections: int = 20,
    ):
        """
        Initialize the PostgreSQL storage adapter.
        
        Args:
            host: PostgreSQL server host
            port: PostgreSQL server port
            database: Database name
            user: Database user
            password: Database password
            table: Table name for storing data
            sslmode: SSL mode (disable, allow, prefer, require, verify-ca, verify-full)
            connect_timeout: Connection timeout in seconds
            command_timeout: Command timeout in seconds
            max_connections: Maximum number of connections in pool
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.table = table
        self.sslmode = sslmode
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
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
                            "PostgreSQL storage adapter requires the 'psycopg2' package. "
                            "Install with: pip install 'praisonai[postgresql]'"
                        )
                    
                    try:
                        self._pool = pool.ThreadedConnectionPool(
                            minconn=1,
                            maxconn=self.max_connections,
                            host=self.host,
                            port=self.port,
                            database=self.database,
                            user=self.user,
                            password=self.password,
                            sslmode=self.sslmode,
                            connect_timeout=self.connect_timeout,
                        )
                        
                        # Create table if it doesn't exist
                        self._create_table()
                        
                    except Exception as e:
                        raise RuntimeError(f"Failed to create PostgreSQL connection pool: {e}") from e
                        
        return self._pool
    
    def _create_table(self) -> None:
        """Create storage table if it doesn't exist."""
        pool = self._pool
        conn = None
        
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                # Create table with proper indexing
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table} (
                        key VARCHAR(255) PRIMARY KEY,
                        data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Create indexes for better performance
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{self.table}_updated_at 
                    ON {self.table}(updated_at);
                """)
                
                # Create a function and trigger for updated_at
                cur.execute(f"""
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ language 'plpgsql';
                """)
                
                cur.execute(f"""
                    DROP TRIGGER IF EXISTS update_{self.table}_updated_at ON {self.table};
                    CREATE TRIGGER update_{self.table}_updated_at 
                        BEFORE UPDATE ON {self.table} 
                        FOR EACH ROW EXECUTE PROCEDURE update_updated_at_column();
                """)
                
                conn.commit()
                
        except Exception as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to create PostgreSQL table: {e}") from e
        finally:
            if conn:
                pool.putconn(conn)
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key (upsert)."""
        pool = self._get_pool()
        conn = None
        
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                # Convert to JSON for storage
                json_data = json.dumps(data, default=str, ensure_ascii=False)
                
                # Use ON CONFLICT for upsert behavior
                cur.execute(f"""
                    INSERT INTO {self.table} (key, data, created_at, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET
                        data = EXCLUDED.data,
                        updated_at = CURRENT_TIMESTAMP;
                """, (key, json_data))
                
                conn.commit()
                
        except Exception as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to save data to PostgreSQL: {e}") from e
        finally:
            if conn:
                pool.putconn(conn)
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        pool = self._get_pool()
        conn = None
        
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT data FROM {self.table} WHERE key = %s;
                """, (key,))
                
                row = cur.fetchone()
                if row:
                    try:
                        # Data is stored as JSON string
                        return json.loads(row[0])
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Invalid JSON data for key '{key}': {e}") from e
                return None
                
        except Exception as e:
            raise RuntimeError(f"Failed to load data from PostgreSQL: {e}") from e
        finally:
            if conn:
                pool.putconn(conn)
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        pool = self._get_pool()
        conn = None
        
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                cur.execute(f"""
                    DELETE FROM {self.table} WHERE key = %s;
                """, (key,))
                
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
                
        except Exception as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to delete data from PostgreSQL: {e}") from e
        finally:
            if conn:
                pool.putconn(conn)
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        pool = self._get_pool()
        conn = None
        
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                if prefix:
                    cur.execute(f"""
                        SELECT key FROM {self.table}
                        WHERE key LIKE %s
                        ORDER BY key;
                    """, (f"{prefix}%",))
                else:
                    cur.execute(f"""
                        SELECT key FROM {self.table}
                        ORDER BY key;
                    """)
                
                return [row[0] for row in cur.fetchall()]
                
        except Exception as e:
            raise RuntimeError(f"Failed to list keys from PostgreSQL: {e}") from e
        finally:
            if conn:
                pool.putconn(conn)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        pool = self._get_pool()
        conn = None
        
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT 1 FROM {self.table} WHERE key = %s LIMIT 1;
                """, (key,))
                
                return cur.fetchone() is not None
                
        except Exception as e:
            raise RuntimeError(f"Failed to check key existence in PostgreSQL: {e}") from e
        finally:
            if conn:
                pool.putconn(conn)
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        pool = self._get_pool()
        conn = None
        
        try:
            conn = pool.getconn()
            with conn.cursor() as cur:
                # Count first
                cur.execute(f"SELECT COUNT(*) FROM {self.table};")
                count = cur.fetchone()[0]
                
                # Then delete all
                cur.execute(f"DELETE FROM {self.table};")
                conn.commit()
                
                return count
                
        except Exception as e:
            if conn:
                conn.rollback()
            raise RuntimeError(f"Failed to clear data from PostgreSQL: {e}") from e
        finally:
            if conn:
                pool.putconn(conn)
    
    def ping(self) -> bool:
        """Test connection to PostgreSQL."""
        try:
            pool = self._get_pool()
            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    return cur.fetchone() is not None
            finally:
                pool.putconn(conn)
        except Exception:
            return False
    
    def close(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            try:
                self._pool.closeall()
            finally:
                self._pool = None