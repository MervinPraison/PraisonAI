"""
Redis implementation of StateStore.

Requires: redis
Install: pip install redis
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import StateStore
from ...storage import RedisStorageAdapter

logger = logging.getLogger(__name__)


class RedisStateStore(StateStore):
    """
    Redis-based state store for fast key-value operations.
    
    This is now a thin wrapper around RedisStorageAdapter to avoid duplication.
    
    Example:
        store = RedisStateStore(
            url="redis://localhost:6379"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        prefix: str = "praison:",
        decode_responses: bool = True,
        socket_timeout: int = 5,
        max_connections: int = 10,
    ):
        """
        Initialize Redis state store.
        
        Args:
            url: Full Redis URL (overrides host/port/db/password)
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password
            prefix: Key prefix for namespacing
            decode_responses: Decode bytes to strings (for compatibility, not used)
            socket_timeout: Socket timeout in seconds
            max_connections: Max connections in pool (for compatibility, not used)
        """
        # Build URL from components if not provided
        if not url:
            if password:
                url = f"redis://:{password}@{host}:{port}/{db}"
            else:
                url = f"redis://{host}:{port}/{db}"
        
        # Use the canonical storage adapter
        self._adapter = RedisStorageAdapter(
            url=url,
            prefix=prefix,
            db=db,
            password=password,
            socket_timeout=float(socket_timeout),
        )
        
        # Store for compatibility
        self.prefix = prefix
        
        # Keep reference to redis client for advanced operations
        self._client = self._adapter._get_client()
        
        logger.info(f"Connected to Redis at {url}")
    
    def _key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.prefix}{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        data = self._adapter.load(key)
        if data is None:
            return None
        # Unwrap value if it was wrapped for dict storage
        if isinstance(data, dict) and "value" in data and len(data) == 1:
            return data["value"]
        return data
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set a value with optional TTL."""
        # Wrap non-dict values for adapter (expects dict)
        if not isinstance(value, dict):
            value = {"value": value}
        
        # Store TTL in adapter if needed
        if ttl:
            # Create new adapter instance with TTL
            adapter_with_ttl = RedisStorageAdapter(
                url=self._adapter.url,
                prefix=self._adapter.prefix,
                ttl=ttl,
                db=self._adapter.db,
                password=self._adapter.password,
                socket_timeout=self._adapter.socket_timeout,
            )
            adapter_with_ttl.save(key, value)
        else:
            self._adapter.save(key, value)
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        return self._adapter.delete(key)
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return self._client.exists(self._key(key)) > 0
    
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        full_pattern = self._key(pattern)
        keys = self._client.keys(full_pattern)
        # Remove prefix from returned keys
        prefix_len = len(self.prefix)
        return [k[prefix_len:] if k.startswith(self.prefix) else k for k in keys]
    
    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds."""
        result = self._client.ttl(self._key(key))
        if result < 0:  # -1 = no TTL, -2 = key doesn't exist
            return None
        return result
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        return self._client.expire(self._key(key), ttl)
    
    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        value = self._client.hget(self._key(key), field)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash."""
        if not isinstance(value, str):
            value = json.dumps(value)
        self._client.hset(self._key(key), field, value)
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        data = self._client.hgetall(self._key(key))
        result = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash."""
        if not fields:
            return 0
        return self._client.hdel(self._key(key), *fields)
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter."""
        return self._client.incrby(self._key(key), amount)
    
    def decr(self, key: str, amount: int = 1) -> int:
        """Decrement a counter."""
        return self._client.decrby(self._key(key), amount)
    
    def close(self) -> None:
        """Close the store."""
        if self._client:
            self._client.close()
            self._client = None
