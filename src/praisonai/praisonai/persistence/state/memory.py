"""
In-memory / JSON file implementation of StateStore.

Zero external dependencies - uses Python built-ins.
"""

import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


class MemoryStateStore(StateStore):
    """
    In-memory state store with optional JSON file persistence.
    
    Zero external dependencies - ideal for development and testing.
    
    Example:
        # In-memory only
        store = MemoryStateStore()
        
        # With file persistence
        store = MemoryStateStore(path="./state.json")
    """
    
    def __init__(
        self,
        path: Optional[str] = None,
        auto_save: bool = True,
        save_interval: int = 60,
    ):
        """
        Initialize memory state store.
        
        Args:
            path: Path to JSON file for persistence (None = in-memory only)
            auto_save: Auto-save to file periodically
            save_interval: Save interval in seconds
        """
        self.path = path
        self.auto_save = auto_save
        self.save_interval = save_interval
        
        self._data: Dict[str, Any] = {}
        self._ttls: Dict[str, float] = {}  # key -> expiry timestamp
        self._lock = threading.RLock()
        self._last_save = time.time()
        
        # Load from file if exists
        if path and os.path.exists(path):
            self._load()
        
        logger.info(f"MemoryStateStore initialized (path={path})")
    
    def _load(self) -> None:
        """Load state from JSON file."""
        if not self.path:
            return
        
        try:
            with open(self.path, "r") as f:
                saved = json.load(f)
                self._data = saved.get("data", {})
                self._ttls = saved.get("ttls", {})
                
                # Clean expired keys
                now = time.time()
                expired = [k for k, exp in self._ttls.items() if exp <= now]
                for k in expired:
                    self._data.pop(k, None)
                    self._ttls.pop(k, None)
                
            logger.debug(f"Loaded {len(self._data)} keys from {self.path}")
        except Exception as e:
            logger.warning(f"Failed to load state from {self.path}: {e}")
    
    def _save(self) -> None:
        """Save state to JSON file."""
        if not self.path:
            return
        
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w") as f:
                json.dump({"data": self._data, "ttls": self._ttls}, f)
            self._last_save = time.time()
        except Exception as e:
            logger.warning(f"Failed to save state to {self.path}: {e}")
    
    def _maybe_save(self) -> None:
        """Save if auto_save is enabled and interval has passed."""
        if self.auto_save and self.path:
            if time.time() - self._last_save >= self.save_interval:
                self._save()
    
    def _check_ttl(self, key: str) -> bool:
        """Check if key is expired. Returns True if valid, False if expired."""
        if key not in self._ttls:
            return True
        if self._ttls[key] <= time.time():
            self._data.pop(key, None)
            self._ttls.pop(key, None)
            return False
        return True
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        with self._lock:
            if not self._check_ttl(key):
                return None
            return self._data.get(key)
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set a value with optional TTL."""
        with self._lock:
            self._data[key] = value
            if ttl:
                self._ttls[key] = time.time() + ttl
            elif key in self._ttls:
                del self._ttls[key]
            self._maybe_save()
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        with self._lock:
            existed = key in self._data
            self._data.pop(key, None)
            self._ttls.pop(key, None)
            self._maybe_save()
            return existed
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        with self._lock:
            if not self._check_ttl(key):
                return False
            return key in self._data
    
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        import fnmatch
        
        with self._lock:
            # Clean expired keys first
            now = time.time()
            expired = [k for k, exp in self._ttls.items() if exp <= now]
            for k in expired:
                self._data.pop(k, None)
                self._ttls.pop(k, None)
            
            if pattern == "*":
                return list(self._data.keys())
            return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]
    
    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds."""
        with self._lock:
            if key not in self._ttls:
                return None
            remaining = self._ttls[key] - time.time()
            if remaining <= 0:
                self._data.pop(key, None)
                self._ttls.pop(key, None)
                return None
            return int(remaining)
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        with self._lock:
            if key not in self._data:
                return False
            self._ttls[key] = time.time() + ttl
            self._maybe_save()
            return True
    
    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        with self._lock:
            if not self._check_ttl(key):
                return None
            data = self._data.get(key)
            if not isinstance(data, dict):
                return None
            return data.get(field)
    
    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash."""
        with self._lock:
            if key not in self._data or not isinstance(self._data[key], dict):
                self._data[key] = {}
            self._data[key][field] = value
            self._maybe_save()
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        with self._lock:
            if not self._check_ttl(key):
                return {}
            data = self._data.get(key)
            if not isinstance(data, dict):
                return {}
            return dict(data)
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash."""
        with self._lock:
            if key not in self._data or not isinstance(self._data[key], dict):
                return 0
            count = 0
            for field in fields:
                if field in self._data[key]:
                    del self._data[key][field]
                    count += 1
            self._maybe_save()
            return count
    
    def flush(self) -> None:
        """Force save to file."""
        with self._lock:
            self._save()
    
    def clear(self) -> None:
        """Clear all data."""
        with self._lock:
            self._data.clear()
            self._ttls.clear()
            self._maybe_save()
    
    def close(self) -> None:
        """Close the store and save."""
        with self._lock:
            if self.path:
                self._save()
