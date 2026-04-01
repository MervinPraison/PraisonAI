"""
Redis Storage Adapter for PraisonAI Agents.

Provides Redis-based storage implementation following StorageBackendProtocol.
Uses lazy imports for the optional Redis dependency.

Example:
    ```python
    from praisonaiagents.storage import RedisStorageAdapter
    
    adapter = RedisStorageAdapter(url="redis://localhost:6379")
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    ```
"""

import json
import time
import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class RedisStorageAdapter:
    """
    Redis-based storage adapter implementing StorageBackendProtocol.
    
    Uses Redis for high-speed caching and ephemeral data storage.
    Requires the `redis` package (optional dependency).
    Thread-safe with connection pooling.
    """
    
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        prefix: str = "praison:",
        ttl: Optional[int] = None,
        db: int = 0,
        max_connections: int = 10,
    ):
        """
        Initialize the Redis storage adapter.
        
        Args:
            url: Redis connection URL
            prefix: Key prefix for all stored data
            ttl: Optional TTL in seconds for all keys
            db: Redis database number
            max_connections: Max connections in pool
        """
        self.url = url
        self.prefix = prefix
        self.ttl = ttl
        self.db = db
        self.max_connections = max_connections
        self._client = None
        self._lock = threading.Lock()
    
    def _get_client(self):
        """Lazy initialize Redis client with connection pooling."""
        if self._client is None:
            with self._lock:
                if self._client is None:  # Double-check locking
                    try:
                        import redis
                    except ImportError:
                        raise ImportError(
                            "Redis storage adapter requires the 'redis' package. "
                            "Install with: pip install praisonaiagents[redis]"
                        )
                    
                    # Create connection pool for thread safety
                    pool = redis.ConnectionPool.from_url(
                        self.url,
                        db=self.db,
                        max_connections=self.max_connections,
                        retry_on_timeout=True,
                        health_check_interval=30
                    )
                    self._client = redis.Redis(connection_pool=pool)
                    
                    # Test connection
                    try:
                        self._client.ping()
                        logger.info(f"Connected to Redis at {self.url}")
                    except Exception as e:
                        logger.error(f"Failed to connect to Redis: {e}")
                        raise
        return self._client
    
    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.prefix}{key}"
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        try:
            client = self._get_client()
            full_key = self._make_key(key)
            json_data = json.dumps(data, default=str, ensure_ascii=False)
            
            if self.ttl:
                client.setex(full_key, self.ttl, json_data)
            else:
                client.set(full_key, json_data)
                
            logger.debug(f"Saved data to Redis key: {key}")
        except Exception as e:
            logger.error(f"Failed to save data to Redis key {key}: {e}")
            raise
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        try:
            client = self._get_client()
            full_key = self._make_key(key)
            
            value = client.get(full_key)
            if value:
                try:
                    return json.loads(value)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode JSON for key {key}: {e}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to load data from Redis key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        try:
            client = self._get_client()
            full_key = self._make_key(key)
            result = client.delete(full_key) > 0
            if result:
                logger.debug(f"Deleted Redis key: {key}")
            return result
        except Exception as e:
            logger.error(f"Failed to delete Redis key {key}: {e}")
            return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        try:
            client = self._get_client()
            pattern = self._make_key(f"{prefix}*")
            
            keys = []
            for key in client.keys(pattern):
                # Remove the prefix to return clean keys
                key_str = key.decode() if isinstance(key, bytes) else key
                clean_key = key_str[len(self.prefix):]
                keys.append(clean_key)
            
            return sorted(keys)
        except Exception as e:
            logger.error(f"Failed to list Redis keys: {e}")
            return []
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        try:
            client = self._get_client()
            full_key = self._make_key(key)
            return client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"Failed to check existence of Redis key {key}: {e}")
            return False
    
    def clear(self) -> int:
        """Clear all data with our prefix. Returns number of items deleted."""
        try:
            client = self._get_client()
            pattern = self._make_key("*")
            keys = list(client.keys(pattern))
            
            if keys:
                count = client.delete(*keys)
                logger.info(f"Cleared {count} keys from Redis")
                return count
            return 0
        except Exception as e:
            logger.error(f"Failed to clear Redis data: {e}")
            return 0
    
    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set TTL on a specific key."""
        try:
            client = self._get_client()
            full_key = self._make_key(key)
            return client.expire(full_key, ttl)
        except Exception as e:
            logger.error(f"Failed to set TTL on Redis key {key}: {e}")
            return False
    
    def get_ttl(self, key: str) -> int:
        """Get remaining TTL for a key. Returns -1 if no TTL, -2 if key doesn't exist."""
        try:
            client = self._get_client()
            full_key = self._make_key(key)
            return client.ttl(full_key)
        except Exception as e:
            logger.error(f"Failed to get TTL for Redis key {key}: {e}")
            return -2
    
    def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            try:
                self._client.close()
                logger.debug("Closed Redis connection")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._client = None


__all__ = ['RedisStorageAdapter']