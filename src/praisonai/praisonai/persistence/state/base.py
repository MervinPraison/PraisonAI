"""
Base interfaces for StateStore.

StateStore handles fast key-value state and caching.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import json


class StateStore(ABC):
    """
    Abstract base class for key-value state persistence.
    
    Implementations handle fast state/cache storage for different backends:
    - Redis (dedicated KV store)
    - DynamoDB, Firestore (serverless document stores)
    - MongoDB (document store)
    - Upstash (serverless Redis)
    - In-memory / JSON file (zero-dependency fallback)
    """
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key. Returns None if not found."""
        raise NotImplementedError
    
    @abstractmethod
    def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> None:
        """Set a value. TTL is in seconds."""
        raise NotImplementedError
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if key existed."""
        raise NotImplementedError
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        raise NotImplementedError
    
    @abstractmethod
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        raise NotImplementedError
    
    @abstractmethod
    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds. Returns None if no TTL or key doesn't exist."""
        raise NotImplementedError
    
    @abstractmethod
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key. Returns True if key exists."""
        raise NotImplementedError
    
    def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize JSON value."""
        value = self.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return value
    
    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Serialize and set JSON value."""
        self.set(key, json.dumps(value), ttl)
    
    @abstractmethod
    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        raise NotImplementedError
    
    @abstractmethod
    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash."""
        raise NotImplementedError
    
    @abstractmethod
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        raise NotImplementedError
    
    @abstractmethod
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash. Returns count deleted."""
        raise NotImplementedError
    
    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""
        raise NotImplementedError
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
