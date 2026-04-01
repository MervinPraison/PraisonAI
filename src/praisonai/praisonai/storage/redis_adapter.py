"""
Redis Storage Adapter for PraisonAI.

Implements StorageBackendProtocol using Redis for high-speed storage.
This is the wrapper implementation that contains the heavy Redis dependency.
"""

import json
from typing import Dict, Any, List, Optional


class RedisStorageAdapter:
    """
    Redis-based storage backend adapter.
    
    Uses Redis for high-speed caching and ephemeral data storage.
    Implements StorageBackendProtocol from praisonaiagents.storage.protocols.
    
    Example:
        ```python
        from praisonai.storage import RedisStorageAdapter
        
        adapter = RedisStorageAdapter(url="redis://localhost:6379")
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """
    
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        prefix: str = "praisonai:",
        ttl: Optional[int] = None,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
    ):
        """
        Initialize the Redis storage adapter.
        
        Args:
            url: Redis connection URL
            prefix: Key prefix for all stored data
            ttl: Optional TTL in seconds for all keys
            db: Redis database number
            password: Optional Redis password
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Socket connection timeout in seconds
            retry_on_timeout: Whether to retry on timeout
        """
        self.url = url
        self.prefix = prefix
        self.ttl = ttl
        self.db = db
        self.password = password
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self._client = None
    
    def _get_client(self):
        """Lazy initialize Redis client."""
        if self._client is None:
            try:
                import redis
            except ImportError:
                raise ImportError(
                    "Redis storage adapter requires the 'redis' package. "
                    "Install with: pip install 'praisonai[redis]'"
                )
            
            # Parse URL and add additional parameters
            self._client = redis.from_url(
                self.url,
                db=self.db,
                password=self.password,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry_on_timeout=self.retry_on_timeout,
                decode_responses=False,  # We handle encoding/decoding manually
            )
        return self._client
    
    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.prefix}{key}"
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        client = self._get_client()
        full_key = self._make_key(key)
        json_data = json.dumps(data, default=str, ensure_ascii=False).encode('utf-8')
        
        try:
            if self.ttl:
                client.setex(full_key, self.ttl, json_data)
            else:
                client.set(full_key, json_data)
        except Exception as e:
            raise RuntimeError(f"Failed to save data to Redis: {e}") from e
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        client = self._get_client()
        full_key = self._make_key(key)
        
        try:
            value = client.get(full_key)
            if value:
                try:
                    # Handle both bytes and string values
                    if isinstance(value, bytes):
                        value = value.decode('utf-8')
                    return json.loads(value)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON data for key '{key}': {e}") from e
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to load data from Redis: {e}") from e
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        client = self._get_client()
        full_key = self._make_key(key)
        
        try:
            return client.delete(full_key) > 0
        except Exception as e:
            raise RuntimeError(f"Failed to delete data from Redis: {e}") from e
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        client = self._get_client()
        pattern = self._make_key(f"{prefix}*")
        
        try:
            keys = []
            for key in client.keys(pattern):
                # Remove the prefix to return clean keys
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                clean_key = key_str[len(self.prefix):]
                keys.append(clean_key)
            
            return sorted(keys)
        except Exception as e:
            raise RuntimeError(f"Failed to list keys from Redis: {e}") from e
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        client = self._get_client()
        full_key = self._make_key(key)
        
        try:
            return client.exists(full_key) > 0
        except Exception as e:
            raise RuntimeError(f"Failed to check key existence in Redis: {e}") from e
    
    def clear(self) -> int:
        """Clear all data with our prefix. Returns number of items deleted."""
        client = self._get_client()
        pattern = self._make_key("*")
        
        try:
            keys = list(client.keys(pattern))
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as e:
            raise RuntimeError(f"Failed to clear data from Redis: {e}") from e
    
    def set_ttl(self, key: str, ttl: int) -> bool:
        """Set TTL on a specific key."""
        client = self._get_client()
        full_key = self._make_key(key)
        
        try:
            return client.expire(full_key, ttl)
        except Exception as e:
            raise RuntimeError(f"Failed to set TTL in Redis: {e}") from e
    
    def ping(self) -> bool:
        """Test connection to Redis."""
        try:
            client = self._get_client()
            return client.ping()
        except Exception:
            return False
    
    def close(self) -> None:
        """Close the Redis connection."""
        if self._client:
            try:
                self._client.close()
            finally:
                self._client = None