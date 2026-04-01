"""
Redis Storage Adapter for PraisonAI Agents.

Provides Redis-based storage backend implementing StorageBackendProtocol.
Uses lazy imports for the redis dependency to avoid module-level import overhead.

Example:
    ```python
    from praisonaiagents.storage import RedisStorageAdapter
    
    # Basic usage with defaults
    adapter = RedisStorageAdapter()
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    
    # Custom Redis configuration
    adapter = RedisStorageAdapter(
        host="localhost",
        port=6379,
        db=0,
        password="secret",
        prefix="myapp:"
    )
    ```
"""

import json
import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class RedisStorageAdapter:
    """
    Redis-based storage backend implementing StorageBackendProtocol.
    
    Stores data as JSON strings in Redis with configurable key prefixes.
    Thread-safe and supports connection pooling.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        prefix: str = "praisonai:",
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        **kwargs
    ):
        """
        Initialize Redis storage adapter.
        
        Args:
            host: Redis host address
            port: Redis port number
            db: Redis database number
            password: Redis password (optional)
            prefix: Key prefix for all stored data
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
            **kwargs: Additional Redis connection parameters
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.prefix = prefix
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.connection_kwargs = kwargs
        self._client = None
        self._lock = threading.Lock()
    
    def _get_client(self):
        """Get Redis client with lazy initialization and connection pooling."""
        if self._client is None:
            with self._lock:
                if self._client is None:
                    try:
                        import redis
                    except ImportError:
                        raise ImportError(
                            "Redis not installed. Install with: pip install praisonaiagents[redis]"
                        )
                    
                    self._client = redis.Redis(
                        host=self.host,
                        port=self.port,
                        db=self.db,
                        password=self.password,
                        socket_timeout=self.socket_timeout,
                        socket_connect_timeout=self.socket_connect_timeout,
                        decode_responses=True,
                        **self.connection_kwargs
                    )
                    
                    # Test connection
                    try:
                        self._client.ping()
                    except Exception as e:
                        self._client = None
                        raise ConnectionError(f"Failed to connect to Redis: {e}")
        
        return self._client
    
    def _make_key(self, key: str) -> str:
        """Create prefixed Redis key."""
        return f"{self.prefix}{key}"
    
    def _strip_prefix(self, redis_key: str) -> str:
        """Strip prefix from Redis key."""
        if redis_key.startswith(self.prefix):
            return redis_key[len(self.prefix):]
        return redis_key
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """
        Save data to Redis as JSON.
        
        Args:
            key: Unique identifier for the data
            data: Dictionary to save
            
        Raises:
            ConnectionError: If Redis is unavailable
            ValueError: If data cannot be serialized
        """
        client = self._get_client()
        redis_key = self._make_key(key)
        
        try:
            json_data = json.dumps(data, default=str)
            client.set(redis_key, json_data)
            logger.debug(f"Saved data to Redis key: {redis_key}")
        except Exception as e:
            logger.error(f"Failed to save data to Redis key {redis_key}: {e}")
            raise
    
    def load(self, key: str) -> Any:
        """
        Load data from Redis.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            The stored data, or None if not found
            
        Raises:
            ConnectionError: If Redis is unavailable
            ValueError: If stored data is invalid JSON
        """
        client = self._get_client()
        redis_key = self._make_key(key)
        
        try:
            json_data = client.get(redis_key)
            if json_data is None:
                logger.debug(f"No data found for Redis key: {redis_key}")
                return None
            
            data = json.loads(json_data)
            logger.debug(f"Loaded data from Redis key: {redis_key}")
            return data
        except Exception as e:
            logger.error(f"Failed to load data from Redis key {redis_key}: {e}")
            raise
    
    def delete(self, key: str) -> bool:
        """
        Delete data from Redis.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ConnectionError: If Redis is unavailable
        """
        client = self._get_client()
        redis_key = self._make_key(key)
        
        try:
            result = client.delete(redis_key)
            success = result > 0
            if success:
                logger.debug(f"Deleted Redis key: {redis_key}")
            else:
                logger.debug(f"Redis key not found for deletion: {redis_key}")
            return success
        except Exception as e:
            logger.error(f"Failed to delete Redis key {redis_key}: {e}")
            raise
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """
        List all keys, optionally filtered by prefix.
        
        Args:
            prefix: Optional prefix to filter keys (applied after the Redis prefix)
            
        Returns:
            List of matching keys (without Redis prefix)
            
        Raises:
            ConnectionError: If Redis is unavailable
        """
        client = self._get_client()
        search_pattern = f"{self.prefix}{prefix}*"
        
        try:
            redis_keys = client.keys(search_pattern)
            keys = [self._strip_prefix(k) for k in redis_keys]
            logger.debug(f"Found {len(keys)} keys matching pattern: {search_pattern}")
            return sorted(keys)
        except Exception as e:
            logger.error(f"Failed to list Redis keys with pattern {search_pattern}: {e}")
            raise
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in Redis.
        
        Args:
            key: Unique identifier to check
            
        Returns:
            True if exists, False otherwise
            
        Raises:
            ConnectionError: If Redis is unavailable
        """
        client = self._get_client()
        redis_key = self._make_key(key)
        
        try:
            result = client.exists(redis_key)
            exists = result > 0
            logger.debug(f"Redis key {'exists' if exists else 'does not exist'}: {redis_key}")
            return exists
        except Exception as e:
            logger.error(f"Failed to check existence of Redis key {redis_key}: {e}")
            raise
    
    def close(self) -> None:
        """Close Redis connection if open."""
        if self._client is not None:
            try:
                self._client.close()
                logger.debug("Closed Redis connection")
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {e}")
            finally:
                self._client = None


__all__ = ["RedisStorageAdapter"]