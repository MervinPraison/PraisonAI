"""
Valkey implementation of StateStore.

Requires: valkey-glide-sync
Install: pip install 'praisonai[valkey]'
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


def create_valkey_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    password: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Create a Valkey client with consistent configuration across modules.
    
    Args:
        host: Valkey host (default from VALKEY_HOST env var or "localhost")
        port: Valkey port (default from VALKEY_PORT env var or 6379)
        password: Valkey password (default from VALKEY_PASSWORD env var)
        **kwargs: Additional client configuration
    
    Returns:
        Configured Valkey client instance
    """
    try:
        from glide import GlideClient, NodeAddress
        from glide.config import GlideClientConfiguration
    except ImportError:
        raise ImportError(
            "valkey-glide-sync is required for Valkey support. "
            "Install with: pip install 'praisonai[valkey]' or pip install valkey-glide-sync>=2.3.1"
        )
    
    # Resolve connection parameters from env vars or defaults
    host = host or os.getenv("VALKEY_HOST", "localhost")
    port = port or int(os.getenv("VALKEY_PORT", "6379"))
    password = password or os.getenv("VALKEY_PASSWORD")
    
    # Build client configuration
    addresses = [NodeAddress(host, port)]
    
    config = GlideClientConfiguration(
        addresses=addresses,
        credentials={"password": password} if password else None,
        **kwargs
    )
    
    return GlideClient(config)


class ValkeyStateStore(StateStore):
    """
    Valkey-based state store for fast key-value operations.
    
    Uses valkey-glide-sync for optimal performance and native Valkey features.
    
    Example:
        store = ValkeyStateStore(
            host="localhost",
            port=6379,
            password="secret"
        )
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        prefix: str = "praison:",
        **kwargs
    ):
        """
        Initialize Valkey state store.
        
        Args:
            host: Valkey host (default from VALKEY_HOST env var or "localhost")
            port: Valkey port (default from VALKEY_PORT env var or 6379)
            password: Valkey password (default from VALKEY_PASSWORD env var)
            prefix: Key prefix for namespacing
            **kwargs: Additional client configuration
        """
        self.prefix = prefix
        self._client = create_valkey_client(host=host, port=port, password=password, **kwargs)
        
        # Test connection
        try:
            self._client.ping()
            logger.info(f"Connected to Valkey at {host or 'localhost'}:{port or 6379}")
        except Exception as e:
            logger.error(f"Failed to connect to Valkey: {e}")
            raise
    
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
        
        from glide.commands import SetOptions
        
        options = SetOptions()
        if ttl:
            options = SetOptions(expiry_seconds=ttl)
        
        self._client.set(self._key(key), value, options)
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        return self._client.delete([self._key(key)]) > 0
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return self._client.exists([self._key(key)]) > 0
    
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
        self._client.hset(self._key(key), {field: value})
    
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
        return self._client.hdel(self._key(key), fields)
    
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