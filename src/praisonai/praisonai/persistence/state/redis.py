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
        
        # Mask password in log output
        log_url = url
        if password and "@" in url:
            log_url = url.replace(f":{password}@", ":****@")
        logger.info(f"Connected to Redis at {log_url}")
    
    def _key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.prefix}{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        data = self._adapter.load(key)
        if data is None:
            return None
        # Unwrap value if it was wrapped for dict storage (check for marker)
        if isinstance(data, dict) and "__wrapped__" in data and "value" in data:
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
            value = {"value": value, "__wrapped__": True}
        
        # Store with TTL if needed
        if ttl:
            # Use the existing client with setex for TTL
            full_key = self._key(key)
            json_data = json.dumps(value, default=str, ensure_ascii=False)
            self._client.setex(full_key, ttl, json_data)
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
        prefix_bytes = self.prefix.encode('utf-8')
        result = []
        for k in keys:
            # Handle both bytes and string keys
            if isinstance(k, bytes):
                if k.startswith(prefix_bytes):
                    result.append(k[prefix_len:].decode('utf-8'))
                else:
                    result.append(k.decode('utf-8'))
            else:
                if k.startswith(self.prefix):
                    result.append(k[prefix_len:])
                else:
                    result.append(k)
        return result
    
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
            # Handle bytes keys
            field_key = k.decode('utf-8') if isinstance(k, bytes) else k
            # Handle bytes values
            field_val = v
            if isinstance(field_val, bytes):
                try:
                    field_val = json.loads(field_val.decode('utf-8'))
                except (json.JSONDecodeError, ValueError):
                    field_val = field_val.decode('utf-8')
            else:
                try:
                    field_val = json.loads(field_val)
                except (json.JSONDecodeError, TypeError):
                    pass
            result[field_key] = field_val
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
