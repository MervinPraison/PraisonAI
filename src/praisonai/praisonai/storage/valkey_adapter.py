"""
Valkey Storage Adapter for PraisonAI.

Implements StorageBackendProtocol using Valkey for high-speed storage.
This is the wrapper implementation that contains the heavy Valkey dependency.
"""

import json
from typing import Dict, Any, List, Optional

from ..persistence._valkey_client import create_valkey_client, scan_keys


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
        **kwargs: Any,
    ):
        """
        Initialize the Valkey storage adapter.

        Args:
            host:     Valkey host (env ``VALKEY_HOST``, default ``"localhost"``).
            port:     Valkey port (env ``VALKEY_PORT``, default ``6379``).
            password: Valkey password (env ``VALKEY_PASSWORD``, optional).
            prefix:   Key prefix for all stored data (default ``"praisonai:"``).
            ttl:      Optional TTL in seconds applied to every saved key.
            **kwargs: Additional ``GlideClientConfiguration`` options.
        """
        self.prefix = prefix
        self.ttl = ttl
        self._client = create_valkey_client(host=host, port=port, password=password, **kwargs)

        try:
            self._client.ping()
        except Exception as exc:
            raise ConnectionError(f"Failed to connect to Valkey: {exc}") from exc

    def _key(self, key: str) -> str:
        """Return the fully-qualified key with adapter prefix."""
        return f"{self.prefix}{key}"

    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Serialise *data* to JSON and save it under *key*."""
        json_str = json.dumps(data, default=str)
        if self.ttl:
            from glide_sync import ExpirySet, ExpiryType  # type: ignore[import]
            self._client.set(self._key(key), json_str, expiry=ExpirySet(ExpiryType.SEC, self.ttl))
        else:
            self._client.set(self._key(key), json_str)

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load and deserialise the value stored under *key*."""
        raw = self._client.get(self._key(key))
        if raw is None:
            return None
        text = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def delete(self, key: str) -> bool:
        """Delete the entry for *key*. Returns ``True`` if it existed."""
        return self._client.delete([self._key(key)]) > 0

    def list_keys(self, prefix: str = "") -> List[str]:
        """Return all keys that start with *prefix* (adapter prefix excluded)."""
        pattern = self._key(prefix + "*")
        all_keys = scan_keys(self._client, pattern)
        prefix_len = len(self.prefix)
        return [k[prefix_len:] for k in all_keys if k.startswith(self.prefix)]

    def exists(self, key: str) -> bool:
        """Return ``True`` if *key* exists."""
        return self._client.exists([self._key(key)]) > 0

    def clear(self) -> int:
        """Delete all keys managed by this adapter. Returns the count deleted."""
        all_keys = scan_keys(self._client, self._key("*"))
        if all_keys:
            return self._client.delete(all_keys)
        return 0

    def close(self) -> None:
        """Close the adapter and release the underlying connection."""
        if self._client:
            self._client.close()
            self._client = None


# Alias for backward compatibility
ValkeyBackend = ValkeyStorageAdapter