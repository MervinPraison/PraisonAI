"""
Storage Backend Implementations for PraisonAI Agents.

Provides concrete implementations of StorageBackendProtocol:
- FileBackend: JSON file-based storage (default)
- SQLiteBackend: SQLite database storage (optional, zero external deps)

These backends enable switching between file-based and database-based storage
without changing application code.

DRY: All backends implement StorageBackendProtocol for consistent interface.
"""

import json
import os
import time
import threading
import tempfile
import logging
from praisonaiagents._logging import get_logger
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..paths import get_storage_dir, get_storage_path

logger = get_logger(__name__)

# Default storage directory (uses centralized paths - DRY)
DEFAULT_STORAGE_DIR = str(get_storage_dir())

class FileBackend:
    """
    JSON file-based storage backend.
    
    Default backend that stores each key as a separate JSON file.
    Thread-safe with file locking support.
    
    Example:
        ```python
        backend = FileBackend(storage_dir="~/.praisonai/storage")
        backend.save("session_123", {"messages": []})
        data = backend.load("session_123")
        ```
    """
    
    def __init__(
        self,
        storage_dir: str = None,
        suffix: str = ".json",
        pretty: bool = True,
    ):
        """
        Initialize the file backend.
        
        Args:
            storage_dir: Directory to store files
            suffix: File suffix (default: .json)
            pretty: Use pretty-printed JSON
        """
        self.storage_dir = Path(os.path.expanduser(storage_dir or DEFAULT_STORAGE_DIR))
        self.suffix = suffix
        self.pretty = pretty
        self._lock = threading.Lock()
        
        # Create directory if needed
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _key_to_path(self, key: str) -> Path:
        """Convert key to file path."""
        # Sanitize key for filesystem
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.storage_dir / f"{safe_key}{self.suffix}"
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        with self._lock:
            file_path = self._key_to_path(key)
            
            # Atomic write via temp file
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=str(self.storage_dir),
                    delete=False,
                    suffix=".tmp"
                ) as f:
                    if self.pretty:
                        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
                    else:
                        json.dump(data, f, default=str, ensure_ascii=False)
                    temp_path = f.name
                
                os.replace(temp_path, file_path)
            except Exception as e:
                logger.error(f"Failed to save {key}: {e}")
                try:
                    if 'temp_path' in locals():
                        os.remove(temp_path)
                except Exception:
                    pass
                raise
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        file_path = self._key_to_path(key)
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        with self._lock:
            file_path = self._key_to_path(key)
            
            if file_path.exists():
                try:
                    file_path.unlink()
                    return True
                except Exception as e:
                    logger.error(f"Failed to delete {key}: {e}")
                    return False
            return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        keys = []
        
        for file_path in self.storage_dir.iterdir():
            if file_path.is_file() and file_path.suffix == self.suffix:
                key = file_path.stem
                if not prefix or key.startswith(prefix):
                    keys.append(key)
        
        return sorted(keys)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return self._key_to_path(key).exists()
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        count = 0
        with self._lock:
            for file_path in self.storage_dir.iterdir():
                if file_path.is_file() and file_path.suffix == self.suffix:
                    try:
                        file_path.unlink()
                        count += 1
                    except Exception:
                        pass
        return count

class SQLiteBackend:
    """
    SQLite-based storage backend.
    
    Uses Python's built-in sqlite3 module (zero external dependencies).
    Better for concurrent access and large datasets.
    
    Example:
        ```python
        backend = SQLiteBackend(db_path="~/.praisonai/data.db")
        backend.save("session_123", {"messages": []})
        data = backend.load("session_123")
        ```
    """
    
    def __init__(
        self,
        db_path: str = None,
        table_name: str = "praison_storage",
        auto_create: bool = True,
    ):
        """
        Initialize the SQLite backend.
        
        Args:
            db_path: Path to SQLite database file
            table_name: Name of the storage table
            auto_create: Create table if it doesn't exist
        """
        self.db_path = os.path.expanduser(db_path) if db_path else str(get_storage_path())
        self.table_name = table_name
        self._local = threading.local()
        
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        if auto_create:
            self._create_table()
    
    def _get_conn(self):
        """Get thread-local connection."""
        # Lazy import sqlite3
        import sqlite3
        
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent write safety
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.commit()
        return self._local.conn
    
    def _create_table(self) -> None:
        """Create storage table if it doesn't exist."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            )
        """)
        
        # Index for prefix queries
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_name}_key 
            ON {self.table_name}(key)
        """)
        
        conn.commit()
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        json_data = json.dumps(data, default=str, ensure_ascii=False)
        
        cur.execute(f"""
            INSERT INTO {self.table_name} (key, data, updated_at)
            VALUES (?, ?, strftime('%s', 'now'))
            ON CONFLICT(key) DO UPDATE SET
                data = excluded.data,
                updated_at = strftime('%s', 'now')
        """, (key, json_data))
        
        conn.commit()
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        cur.execute(f"""
            SELECT data FROM {self.table_name} WHERE key = ?
        """, (key,))
        
        row = cur.fetchone()
        if row:
            try:
                return json.loads(row["data"])
            except json.JSONDecodeError:
                return None
        return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        cur.execute(f"""
            DELETE FROM {self.table_name} WHERE key = ?
        """, (key,))
        
        deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        if prefix:
            cur.execute(f"""
                SELECT key FROM {self.table_name}
                WHERE key LIKE ?
                ORDER BY key
            """, (f"{prefix}%",))
        else:
            cur.execute(f"""
                SELECT key FROM {self.table_name}
                ORDER BY key
            """)
        
        return [row["key"] for row in cur.fetchall()]
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        cur.execute(f"""
            SELECT 1 FROM {self.table_name} WHERE key = ? LIMIT 1
        """, (key,))
        
        return cur.fetchone() is not None
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        cur.execute(f"SELECT COUNT(*) as count FROM {self.table_name}")
        count = cur.fetchone()["count"]
        
        cur.execute(f"DELETE FROM {self.table_name}")
        conn.commit()
        
        return count
    
    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

class RedisBackend:
    """
    Redis-based storage backend.
    
    Uses Redis for high-speed caching and ephemeral data storage.
    Requires the `redis` package (optional dependency).
    
    Example:
        ```python
        backend = RedisBackend(url="redis://localhost:6379")
        backend.save("session_123", {"messages": []})
        data = backend.load("session_123")
        ```
    """
    
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        prefix: str = "praison:",
        ttl: Optional[int] = None,
        db: int = 0,
    ):
        """
        Initialize the Redis backend.
        
        Args:
            url: Redis connection URL
            prefix: Key prefix for all stored data
            ttl: Optional TTL in seconds for all keys
            db: Redis database number
        """
        self.url = url
        self.prefix = prefix
        self.ttl = ttl
        self.db = db
        self._client = None
    
    def _get_client(self):
        """Lazy initialize Redis client."""
        if self._client is None:
            try:
                import redis
            except ImportError:
                raise ImportError(
                    "Redis backend requires the 'redis' package. "
                    "Install with: pip install redis"
                )
            self._client = redis.from_url(self.url, db=self.db)
        return self._client
    
    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.prefix}{key}"
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        client = self._get_client()
        full_key = self._make_key(key)
        json_data = json.dumps(data, default=str, ensure_ascii=False)
        
        if self.ttl:
            client.setex(full_key, self.ttl, json_data)
        else:
            client.set(full_key, json_data)
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        client = self._get_client()
        full_key = self._make_key(key)
        
        value = client.get(full_key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        client = self._get_client()
        full_key = self._make_key(key)
        return client.delete(full_key) > 0
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        client = self._get_client()
        pattern = self._make_key(f"{prefix}*")
        
        keys = []
        for key in client.keys(pattern):
            # Remove the prefix to return clean keys
            key_str = key.decode() if isinstance(key, bytes) else key
            clean_key = key_str[len(self.prefix):]
            keys.append(clean_key)
        
        return sorted(keys)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        client = self._get_client()
        full_key = self._make_key(key)
        return client.exists(full_key) > 0
    
    def clear(self) -> int:
        """Clear all data with our prefix. Returns number of items deleted."""
        client = self._get_client()
        pattern = self._make_key("*")
        keys = list(client.keys(pattern))
        
        if keys:
            return client.delete(*keys)
        return 0
    
    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set TTL on a specific key."""
        client = self._get_client()
        full_key = self._make_key(key)
        return client.expire(full_key, ttl)
    
    def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            self._client.close()
            self._client = None

class MongoDBBackend:
    """
    MongoDB-based storage backend.
    
    Uses MongoDB for document-oriented data storage.
    Requires the `pymongo` package (optional dependency).
    
    Example:
        ```python
        backend = MongoDBBackend(url="mongodb://localhost:27017/")
        backend.save("session_123", {"messages": []})
        data = backend.load("session_123")
        ```
    """
    
    def __init__(
        self,
        url: str = "mongodb://localhost:27017/",
        database: str = "praisonai",
        collection: str = "praison_storage",
        max_pool_size: int = 50,
    ):
        self.url = url
        self.database = database
        self.collection_name = collection
        self.max_pool_size = max_pool_size
        self._client = None
        self._collection = None
    
    def _get_collection(self):
        """Lazy initialize MongoDB client and collection."""
        if self._collection is None:
            try:
                import pymongo
            except ImportError:
                raise ImportError(
                    "MongoDB backend requires the 'pymongo' package. "
                    "Install with: pip install pymongo"
                )
            self._client = pymongo.MongoClient(
                self.url,
                maxPoolSize=self.max_pool_size,
                retryWrites=True,
                retryReads=True,
                serverSelectionTimeoutMS=5000,  # 5 second timeout for connection
            )
            db = self._client[self.database]
            self._collection = db[self.collection_name]
        return self._collection
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key (upsert)."""
        collection = self._get_collection()
        json_data = json.dumps(data, default=str, ensure_ascii=False)
        collection.replace_one(
            {"_id": key},
            {"_id": key, "data": json_data, "updated_at": time.time()},
            upsert=True,
        )
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        collection = self._get_collection()
        doc = collection.find_one({"_id": key})
        if doc and "data" in doc:
            try:
                return json.loads(doc["data"])
            except json.JSONDecodeError:
                return None
        return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        collection = self._get_collection()
        result = collection.delete_one({"_id": key})
        return result.deleted_count > 0
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        collection = self._get_collection()
        if prefix:
            cursor = collection.find(
                {"_id": {"$regex": f"^{prefix}"}},
                {"_id": 1}
            )
        else:
            cursor = collection.find({}, {"_id": 1})
        return sorted([doc["_id"] for doc in cursor])
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        collection = self._get_collection()
        return collection.count_documents({"_id": key}, limit=1) > 0
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        collection = self._get_collection()
        result = collection.delete_many({})
        return result.deleted_count
    
    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._collection = None

def get_backend(
    backend_type: str = "file",
    **kwargs
) -> Any:
    """
    Factory function to get a storage backend.
    
    Args:
        backend_type: Type of backend ("file", "sqlite", or "redis")
        **kwargs: Backend-specific arguments
        
    Returns:
        Storage backend instance
        
    Example:
        ```python
        # File backend (default)
        backend = get_backend("file", storage_dir="~/.praisonai/data")
        
        # SQLite backend
        backend = get_backend("sqlite", db_path="~/.praisonai/data.db")
        
        # Redis backend
        backend = get_backend("redis", url="redis://localhost:6379")
        ```
    """
    if backend_type == "file":
        return FileBackend(**kwargs)
    elif backend_type == "sqlite":
        return SQLiteBackend(**kwargs)
    elif backend_type == "redis":
        return RedisBackend(**kwargs)
    elif backend_type == "mongodb":
        return MongoDBBackend(**kwargs)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")

__all__ = [
    'FileBackend',
    'SQLiteBackend',
    'RedisBackend',
    'MongoDBBackend',
    'get_backend',
]
