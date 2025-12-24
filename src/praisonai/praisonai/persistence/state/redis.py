"""
Redis implementation of StateStore.

Requires: redis
Install: pip install redis
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


class RedisStateStore(StateStore):
    """
    Redis-based state store for fast key-value operations.
    
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
            decode_responses: Decode bytes to strings
            socket_timeout: Socket timeout in seconds
            max_connections: Max connections in pool
        """
        try:
            import redis as redis_lib
        except ImportError:
            raise ImportError(
                "redis is required for Redis support. "
                "Install with: pip install redis"
            )
        
        self._redis_lib = redis_lib
        self.prefix = prefix
        
        if url:
            self._client = redis_lib.from_url(
                url,
                decode_responses=decode_responses,
                socket_timeout=socket_timeout,
                max_connections=max_connections,
            )
        else:
            pool = redis_lib.ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                socket_timeout=socket_timeout,
                max_connections=max_connections,
            )
            self._client = redis_lib.Redis(connection_pool=pool)
        
        # Test connection
        self._client.ping()
        logger.info(f"Connected to Redis at {url or f'{host}:{port}'}")
    
    def _key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.prefix}{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        value = self._client.get(self._key(key))
        if value is None:
            return None
        # Try to deserialize JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set a value with optional TTL."""
        # Serialize non-string values
        if not isinstance(value, str):
            value = json.dumps(value)
        
        if ttl:
            self._client.setex(self._key(key), ttl, value)
        else:
            self._client.set(self._key(key), value)
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        return self._client.delete(self._key(key)) > 0
    
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
