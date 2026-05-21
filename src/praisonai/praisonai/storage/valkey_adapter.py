"""
Valkey Storage Adapter for PraisonAI.

Implements StorageBackendProtocol using Valkey for high-speed storage.
This is the wrapper implementation that contains the heavy Valkey dependency.
"""

import json
import os
from typing import Dict, Any, List, Optional


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


class ValkeyStorageAdapter:
    """
    Valkey-based storage backend adapter.
    
    Uses Valkey for high-speed caching and ephemeral data storage.
    Implements StorageBackendProtocol from praisonaiagents.storage.protocols.
    
    Example:
        ```python
        from praisonai.storage import ValkeyStorageAdapter
        
        adapter = ValkeyStorageAdapter(host="localhost", port=6379)
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        prefix: str = "praisonai:",
        ttl: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize the Valkey storage adapter.
        
        Args:
            host: Valkey host (default from VALKEY_HOST env var or "localhost")
            port: Valkey port (default from VALKEY_PORT env var or 6379)
            password: Valkey password (default from VALKEY_PASSWORD env var)
            prefix: Key prefix for all stored data
            ttl: Optional TTL in seconds for all keys
            **kwargs: Additional client configuration
        """
        self.prefix = prefix
        self.ttl = ttl
        self._client = create_valkey_client(host=host, port=port, password=password, **kwargs)
        
        # Test connection
        try:
            self._client.ping()
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Valkey: {e}")
    
    def _key(self, key: str) -> str:
        """Generate prefixed key."""
        return f"{self.prefix}{key}"
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        json_str = json.dumps(data, default=str)
        
        if self.ttl:
            from glide.commands import SetOptions
            options = SetOptions(expiry_seconds=self.ttl)
            self._client.set(self._key(key), json_str, options)
        else:
            self._client.set(self._key(key), json_str)
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        value = self._client.get(self._key(key))
        if value is None:
            return None
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        return self._client.delete([self._key(key)]) > 0
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys with optional prefix."""
        pattern = self._key(prefix + "*")
        keys = self._client.keys(pattern)
        
        # Remove the adapter's prefix to return clean keys
        prefix_len = len(self.prefix)
        return [k[prefix_len:] for k in keys if k.startswith(self.prefix)]
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        return self._client.exists([self._key(key)]) > 0
    
    def clear(self) -> int:
        """Clear all data with this adapter's prefix."""
        pattern = self._key("*")
        keys = self._client.keys(pattern)
        
        if keys:
            return self._client.delete(keys)
        return 0
    
    def close(self) -> None:
        """Close the adapter and release connections."""
        if self._client:
            self._client.close()
            self._client = None


# Alias for backward compatibility
ValkeyBackend = ValkeyStorageAdapter