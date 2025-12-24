"""
Upstash implementation of StateStore.

Requires: upstash-redis
Install: pip install upstash-redis
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


class UpstashStateStore(StateStore):
    """
    Upstash-based state store (serverless Redis).
    
    Example:
        store = UpstashStateStore(
            url="https://xxx.upstash.io",
            token="your-token"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        prefix: str = "praison:",
    ):
        try:
            from upstash_redis import Redis
        except ImportError:
            raise ImportError(
                "upstash-redis is required for Upstash support. "
                "Install with: pip install upstash-redis"
            )
        
        url = url or os.getenv("UPSTASH_REDIS_URL")
        token = token or os.getenv("UPSTASH_REDIS_TOKEN")
        
        if not url or not token:
            raise ValueError("Upstash URL and token are required")
        
        self._client = Redis(url=url, token=token)
        self.prefix = prefix
        
        logger.info(f"Connected to Upstash Redis")
    
    def _key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.prefix}{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        value = self._client.get(self._key(key))
        if value is None:
            return None
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
        prefix_len = len(self.prefix)
        return [k[prefix_len:] if k.startswith(self.prefix) else k for k in keys]
    
    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds."""
        result = self._client.ttl(self._key(key))
        if result < 0:
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
    
    def close(self) -> None:
        """Close the store."""
        pass  # Upstash is stateless HTTP
