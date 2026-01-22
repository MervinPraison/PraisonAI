"""
Base JSON Store for PraisonAI Agents.

Provides a common base class for JSON-based storage to eliminate duplication
across BaseStore, TrainingStorage, and similar classes.

DRY: This module extracts the common JSON load/save pattern with:
- Thread-safe operations
- File locking for concurrent access
- Atomic writes
"""

import json
import os
import threading
import tempfile
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from datetime import datetime

from .models import BaseSessionInfo

if TYPE_CHECKING:
    from .protocols import StorageBackendProtocol

logger = logging.getLogger(__name__)


class FileLock:
    """
    Simple file-based lock for cross-process synchronization.
    
    Uses a .lock file alongside the target file.
    """
    
    def __init__(self, path: Path, timeout: float = 10.0):
        """
        Initialize the file lock.
        
        Args:
            path: Path to the file to lock
            timeout: Maximum time to wait for lock (seconds)
        """
        self.lock_path = Path(str(path) + ".lock")
        self.timeout = timeout
        self._fd = None
    
    def __enter__(self):
        """Acquire the lock."""
        import time
        start = time.time()
        
        while True:
            try:
                # Try to create lock file exclusively
                self._fd = os.open(
                    str(self.lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                break
            except FileExistsError:
                if time.time() - start > self.timeout:
                    # Force remove stale lock
                    try:
                        self.lock_path.unlink()
                    except Exception:
                        pass
                    continue
                time.sleep(0.01)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the lock."""
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
        try:
            self.lock_path.unlink()
        except Exception:
            pass
        return False


class BaseJSONStore:
    """
    Base class for JSON-based storage.
    
    Provides thread-safe, file-locked JSON persistence with:
    - Atomic writes (write to temp, then rename)
    - Thread safety (threading.Lock)
    - File locking (FileLock for cross-process)
    - Common load/save pattern
    - Optional pluggable backend (file, sqlite, etc.)
    
    Subclasses should:
    - Set storage_path in __init__
    - Override _default_data() for initial data structure
    
    Usage:
        class MyStore(BaseJSONStore):
            def __init__(self, path: Path):
                super().__init__(path)
            
            def _default_data(self) -> Dict[str, Any]:
                return {"items": []}
            
            def add_item(self, item: str):
                with self._lock:
                    self._data["items"].append(item)
                    self._save()
        
        # With SQLite backend:
        from praisonaiagents.storage import SQLiteBackend
        store = MyStore(path, backend=SQLiteBackend("data.db"))
    """
    
    def __init__(
        self,
        storage_path: Union[Path, str],
        create_if_missing: bool = True,
        use_file_lock: bool = True,
        lock_timeout: float = 10.0,
        backend: Optional["StorageBackendProtocol"] = None,
    ):
        """
        Initialize the store.
        
        Args:
            storage_path: Path to the JSON file (or key for backend)
            create_if_missing: Create parent directories if needed
            use_file_lock: Use file locking for cross-process safety
            lock_timeout: Timeout for file lock acquisition
            backend: Optional storage backend (file, sqlite, etc.)
                     If provided, storage_path is used as the key.
        """
        self.storage_path = Path(storage_path)
        self.use_file_lock = use_file_lock
        self.lock_timeout = lock_timeout
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._backend = backend
        
        if backend is None:
            # File-based storage (default)
            if create_if_missing:
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self.storage_path.exists():
                self._load()
            else:
                self._data = self._default_data()
        else:
            # Backend-based storage
            self._storage_key = self.storage_path.stem
            loaded = backend.load(self._storage_key)
            if loaded is not None:
                self._data = loaded
            else:
                self._data = self._default_data()
    
    def _default_data(self) -> Dict[str, Any]:
        """
        Return default data structure for new stores.
        
        Override in subclasses for custom initial data.
        """
        return {}
    
    def _load(self) -> None:
        """Load data from storage file or backend."""
        if self._backend is not None:
            loaded = self._backend.load(self._storage_key)
            if loaded is not None:
                self._data = loaded
            else:
                self._data = self._default_data()
            return
        
        try:
            if self.use_file_lock:
                with FileLock(self.storage_path, self.lock_timeout):
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
            else:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load {self.storage_path}: {e}")
            self._data = self._default_data()
    
    def _save(self) -> None:
        """Save data to storage file or backend with atomic write."""
        if self._backend is not None:
            try:
                self._backend.save(self._storage_key, self._data)
            except Exception as e:
                logger.error(f"Failed to save to backend: {e}")
                raise
            return
        
        try:
            dir_path = self.storage_path.parent
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Write to temp file first
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(dir_path),
                delete=False,
                suffix=".tmp"
            ) as f:
                json.dump(self._data, f, indent=2, default=str, ensure_ascii=False)
                temp_path = f.name
            
            # Atomic rename
            if self.use_file_lock:
                with FileLock(self.storage_path, self.lock_timeout):
                    os.replace(temp_path, self.storage_path)
            else:
                os.replace(temp_path, self.storage_path)
                
        except Exception as e:
            logger.error(f"Failed to save {self.storage_path}: {e}")
            # Clean up temp file if it exists
            try:
                if 'temp_path' in locals():
                    os.remove(temp_path)
            except Exception:
                pass
            raise
    
    def load(self) -> Dict[str, Any]:
        """
        Load and return data from storage.
        
        Returns:
            The stored data dictionary
        """
        with self._lock:
            self._load()
            return self._data.copy()
    
    def save(self, data: Dict[str, Any]) -> None:
        """
        Save data to storage.
        
        Args:
            data: Data dictionary to save
        """
        with self._lock:
            self._data = data
            self._save()
    
    def exists(self) -> bool:
        """Check if storage file or backend key exists."""
        if self._backend is not None:
            return self._backend.exists(self._storage_key)
        return self.storage_path.exists()
    
    def clear(self) -> None:
        """Clear all stored data."""
        with self._lock:
            self._data = self._default_data()
            self._save()
    
    def delete(self) -> bool:
        """
        Delete the storage file or backend key.
        
        Returns:
            True if deleted, False if file didn't exist
        """
        with self._lock:
            if self._backend is not None:
                result = self._backend.delete(self._storage_key)
                if result:
                    self._data = self._default_data()
                return result
            
            try:
                if self.storage_path.exists():
                    self.storage_path.unlink()
                    self._data = self._default_data()
                    return True
                return False
            except Exception as e:
                logger.error(f"Failed to delete {self.storage_path}: {e}")
                return False


def list_json_sessions(
    storage_dir: Path,
    suffix: str = ".json",
    limit: int = 50,
) -> List[BaseSessionInfo]:
    """
    List all sessions in a directory.
    
    Common utility for listing training sessions, traces, etc.
    
    Args:
        storage_dir: Directory to search
        suffix: File suffix to filter by
        limit: Maximum number of sessions to return
        
    Returns:
        List of BaseSessionInfo, sorted by modification time (newest first)
    """
    if not storage_dir.exists():
        return []
    
    sessions = []
    for file_path in storage_dir.iterdir():
        if file_path.is_file() and file_path.suffix == suffix:
            try:
                info = BaseSessionInfo.from_path(file_path)
                
                # Try to get item count from file
                if suffix == ".json":
                    try:
                        with open(file_path, "r") as f:
                            data = json.load(f)
                            # Common patterns for item count
                            if "iterations" in data:
                                info.item_count = len(data["iterations"])
                            elif "messages" in data:
                                info.item_count = len(data["messages"])
                            elif "items" in data:
                                info.item_count = len(data["items"])
                    except Exception:
                        pass
                elif suffix == ".jsonl":
                    try:
                        with open(file_path, "r") as f:
                            info.item_count = sum(1 for _ in f)
                    except Exception:
                        pass
                
                sessions.append(info)
            except Exception as e:
                logger.warning(f"Failed to stat {file_path}: {e}")
    
    # Sort by modification time (newest first)
    sessions.sort(key=lambda s: s.modified_at, reverse=True)
    
    return sessions[:limit]


def cleanup_old_sessions(
    storage_dir: Path,
    suffix: str = ".json",
    max_age_days: int = 30,
    max_size_mb: int = 100,
) -> int:
    """
    Clean up old session files.
    
    Common utility for cleaning up training sessions, traces, etc.
    
    Args:
        storage_dir: Directory to clean
        suffix: File suffix to filter by
        max_age_days: Delete sessions older than this
        max_size_mb: Delete oldest sessions if total size exceeds this
        
    Returns:
        Number of files deleted
    """
    if not storage_dir.exists():
        return 0
    
    deleted = 0
    now = datetime.now()
    
    # Get all sessions sorted by age (oldest first)
    sessions = list_json_sessions(storage_dir, suffix, limit=10000)
    sessions.sort(key=lambda s: s.modified_at)
    
    # Delete old sessions
    for session in sessions:
        age_days = (now - session.modified_at).days
        if age_days > max_age_days:
            try:
                session.path.unlink()
                deleted += 1
            except Exception:
                pass
    
    # Check total size and delete oldest if needed
    remaining = [s for s in sessions if s.path.exists()]
    total_size_mb = sum(s.size_bytes for s in remaining) / (1024 * 1024)
    
    if total_size_mb > max_size_mb:
        for session in remaining:
            if total_size_mb <= max_size_mb:
                break
            try:
                session.path.unlink()
                total_size_mb -= session.size_bytes / (1024 * 1024)
                deleted += 1
            except Exception:
                pass
    
    return deleted


class AsyncBaseJSONStore:
    """
    Async version of BaseJSONStore.
    
    Provides async-safe JSON persistence with optional pluggable backends.
    Uses asyncio locks for thread safety in async contexts.
    
    Usage:
        store = AsyncBaseJSONStore("data.json")
        await store.load_async()
        await store.save_async({"key": "value"})
    """
    
    def __init__(
        self,
        storage_path: Union[Path, str],
        create_if_missing: bool = True,
        backend: Optional["StorageBackendProtocol"] = None,
    ):
        """
        Initialize the async store.
        
        Args:
            storage_path: Path to the JSON file (or key for backend)
            create_if_missing: Create parent directories if needed
            backend: Optional async storage backend
        """
        self.storage_path = Path(storage_path)
        self._backend = backend
        self._data: Dict[str, Any] = {}
        self._async_lock: Optional[Any] = None  # Lazy init asyncio.Lock
        
        if backend is None and create_if_missing:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._storage_key = self.storage_path.stem
    
    def _get_async_lock(self):
        """Lazy initialize asyncio lock."""
        if self._async_lock is None:
            import asyncio
            self._async_lock = asyncio.Lock()
        return self._async_lock
    
    def _default_data(self) -> Dict[str, Any]:
        """Return default data structure."""
        return {}
    
    async def load_async(self) -> Dict[str, Any]:
        """Load data asynchronously."""
        async with self._get_async_lock():
            if self._backend is not None:
                # Check if backend has async method
                if hasattr(self._backend, 'load') and callable(self._backend.load):
                    import asyncio
                    if asyncio.iscoroutinefunction(self._backend.load):
                        loaded = await self._backend.load(self._storage_key)
                    else:
                        loaded = self._backend.load(self._storage_key)
                    self._data = loaded if loaded is not None else self._default_data()
            else:
                # File-based async read
                import aiofiles
                try:
                    async with aiofiles.open(self.storage_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                        self._data = json.loads(content)
                except (FileNotFoundError, json.JSONDecodeError):
                    self._data = self._default_data()
            
            return self._data.copy()
    
    async def save_async(self, data: Dict[str, Any]) -> None:
        """Save data asynchronously."""
        async with self._get_async_lock():
            self._data = data
            
            if self._backend is not None:
                import asyncio
                if asyncio.iscoroutinefunction(self._backend.save):
                    await self._backend.save(self._storage_key, self._data)
                else:
                    self._backend.save(self._storage_key, self._data)
            else:
                # File-based async write
                import aiofiles
                self.storage_path.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(self.storage_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(self._data, indent=2, default=str, ensure_ascii=False))
    
    async def exists_async(self) -> bool:
        """Check if storage exists asynchronously."""
        if self._backend is not None:
            import asyncio
            if asyncio.iscoroutinefunction(self._backend.exists):
                return await self._backend.exists(self._storage_key)
            return self._backend.exists(self._storage_key)
        return self.storage_path.exists()
    
    async def delete_async(self) -> bool:
        """Delete storage asynchronously."""
        async with self._get_async_lock():
            if self._backend is not None:
                import asyncio
                if asyncio.iscoroutinefunction(self._backend.delete):
                    result = await self._backend.delete(self._storage_key)
                else:
                    result = self._backend.delete(self._storage_key)
                if result:
                    self._data = self._default_data()
                return result
            
            if self.storage_path.exists():
                self.storage_path.unlink()
                self._data = self._default_data()
                return True
            return False


__all__ = [
    'FileLock',
    'BaseJSONStore',
    'AsyncBaseJSONStore',
    'list_json_sessions',
    'cleanup_old_sessions',
]
