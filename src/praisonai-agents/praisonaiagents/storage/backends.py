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

class _LazyStorageModule:
    """
    Lazy proxy for heavy storage backends.
    
    Allows access to Redis, MongoDB, PostgreSQL, and DynamoDB adapters
    without importing heavy dependencies in the core SDK.
    Actual backend classes are loaded only when accessed from the wrapper.
    """
    
    _BACKENDS = {
        "RedisBackend": "praisonai.storage",
        "MongoDBBackend": "praisonai.storage", 
        "PostgreSQLBackend": "praisonai.storage",
        "DynamoDBBackend": "praisonai.storage",
        # Legacy names for compatibility
        "RedisStorageAdapter": "praisonai.storage",
        "MongoDBStorageAdapter": "praisonai.storage",
        "PostgreSQLStorageAdapter": "praisonai.storage", 
        "DynamoDBStorageAdapter": "praisonai.storage",
    }
    
    def __getattr__(self, name: str):
        if name in self._BACKENDS:
            try:
                import importlib
                module = importlib.import_module(self._BACKENDS[name])
                # Try both adapter and backend naming
                for attr_name in [name, name.replace("Backend", "StorageAdapter")]:
                    if hasattr(module, attr_name):
                        return getattr(module, attr_name)
                raise AttributeError(f"module '{self._BACKENDS[name]}' has no attribute {name!r}")
            except ImportError as e:
                raise ImportError(
                    f"Storage backend '{name}' requires the praisonai package. "
                    f"Install with: pip install praisonai\n"
                    f"For specific backends, use: pip install 'praisonai[redis]', 'praisonai[mongodb]', etc.\n"
                    f"Original error: {e}"
                ) from e
        raise AttributeError(f"module 'storage' has no attribute {name!r}")
    
    def __repr__(self):
        return "<module 'praisonaiagents.storage' (lazy heavy backends)>"


# Create lazy module instances
_heavy_backends = _LazyStorageModule()

# Expose heavy backends via lazy loading
RedisBackend = _heavy_backends.RedisBackend
MongoDBBackend = _heavy_backends.MongoDBBackend
PostgreSQLBackend = _heavy_backends.PostgreSQLBackend
DynamoDBBackend = _heavy_backends.DynamoDBBackend

def get_backend(
    backend_type: str = "file",
    **kwargs
) -> Any:
    """
    Factory function to get a storage backend.
    
    Args:
        backend_type: Type of backend ("file", "sqlite", "redis", "mongodb", "postgresql", "dynamodb")
        **kwargs: Backend-specific arguments
        
    Returns:
        Storage backend instance
        
    Example:
        ```python
        # File backend (default) - lightweight, in core SDK
        backend = get_backend("file", storage_dir="~/.praisonai/data")
        
        # SQLite backend - lightweight, in core SDK
        backend = get_backend("sqlite", db_path="~/.praisonai/data.db")
        
        # Heavy backends - from wrapper, require praisonai package
        backend = get_backend("redis", url="redis://localhost:6379")
        backend = get_backend("mongodb", url="mongodb://localhost:27017/")
        backend = get_backend("postgresql", host="localhost", database="praisonai")
        backend = get_backend("dynamodb", table_name="praisonai-storage")
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
    elif backend_type == "postgresql":
        return PostgreSQLBackend(**kwargs)
    elif backend_type == "dynamodb":
        return DynamoDBBackend(**kwargs)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}. "
                        f"Supported: file, sqlite, redis, mongodb, postgresql, dynamodb")

__all__ = [
    'FileBackend',
    'SQLiteBackend',
    'RedisBackend',
    'MongoDBBackend', 
    'PostgreSQLBackend',
    'DynamoDBBackend',
    'get_backend',
]
