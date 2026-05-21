"""
Valkey implementation of StateStore.

Requires: valkey-glide-sync
Install: pip install 'praisonai[valkey]'
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import StateStore
from .._valkey_client import create_valkey_client, scan_keys

logger = logging.getLogger(__name__)


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
        **kwargs: Any,
    ):
        """
        Initialize Valkey state store.

        Args:
            host:     Valkey host (env ``VALKEY_HOST``, default ``"localhost"``).
            port:     Valkey port (env ``VALKEY_PORT``, default ``6379``).
            password: Valkey password (env ``VALKEY_PASSWORD``, optional).
            prefix:   Key prefix for namespacing (default ``"praison:"``).
            **kwargs: Additional ``GlideClientConfiguration`` options.
        """
        self.prefix = prefix
        self._client = create_valkey_client(host=host, port=port, password=password, **kwargs)

        try:
            self._client.ping()
            logger.info("Connected to Valkey at %s:%s", host or "localhost", port or 6379)
        except Exception as exc:
            logger.error("Failed to connect to Valkey: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _key(self, key: str) -> str:
        """Return the fully-qualified key with namespace prefix."""
        return f"{self.prefix}{key}"

    @staticmethod
    def _decode(value: Any) -> Any:
        """Decode bytes returned by GlideClient to str."""
        if isinstance(value, (bytes, bytearray)):
            return value.decode()
        return value

    @staticmethod
    def _loads(raw: Any) -> Any:
        """Attempt JSON decode; fall back to plain string."""
        text = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return text

    # ------------------------------------------------------------------
    # StateStore interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        raw = self._client.get(self._key(key))
        if raw is None:
            return None
        return self._loads(raw)

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Set a value with optional TTL (seconds)."""
        serialized = value if isinstance(value, str) else json.dumps(value)
        if ttl:
            from glide_sync import ExpirySet, ExpiryType  # type: ignore[import]
            self._client.set(self._key(key), serialized, expiry=ExpirySet(ExpiryType.SEC, ttl))
        else:
            self._client.set(self._key(key), serialized)

    def delete(self, key: str) -> bool:
        """Delete a key. Returns ``True`` if the key existed."""
        return self._client.delete([self._key(key)]) > 0

    def exists(self, key: str) -> bool:
        """Return ``True`` if the key exists."""
        return self._client.exists([self._key(key)]) > 0

    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching *pattern* (prefix is added automatically)."""
        full_pattern = self._key(pattern)
        all_keys = scan_keys(self._client, full_pattern)
        prefix_len = len(self.prefix)
        return [k[prefix_len:] if k.startswith(self.prefix) else k for k in all_keys]

    def ttl(self, key: str) -> Optional[int]:
        """Return remaining TTL in seconds, or ``None`` if no TTL / missing."""
        result = self._client.ttl(self._key(key))
        if result < 0:  # -1 = no expiry, -2 = key doesn't exist
            return None
        return result

    def expire(self, key: str, ttl: int) -> bool:
        """Set a TTL on an existing key."""
        return self._client.expire(self._key(key), ttl)

    # ------------------------------------------------------------------
    # Hash operations
    # ------------------------------------------------------------------

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a single field from a hash."""
        raw = self._client.hget(self._key(key), field)
        if raw is None:
            return None
        return self._loads(raw)

    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a single field in a hash."""
        serialized = value if isinstance(value, str) else json.dumps(value)
        self._client.hset(self._key(key), {field: serialized})

    def hgetall(self, key: str) -> Dict[str, Any]:
        """Return all fields and values from a hash as a plain dict."""
        raw_map = self._client.hgetall(self._key(key))
        result: Dict[str, Any] = {}
        for k, v in raw_map.items():
            str_key = k.decode() if isinstance(k, (bytes, bytearray)) else k
            result[str_key] = self._loads(v)
        return result

    def hdel(self, key: str, *fields: str) -> int:
        """Delete one or more fields from a hash."""
        if not fields:
            return 0
        return self._client.hdel(self._key(key), list(fields))

    # ------------------------------------------------------------------
    # Counter operations
    # ------------------------------------------------------------------

    def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter by *amount*."""
        return self._client.incrby(self._key(key), amount)

    def decr(self, key: str, amount: int = 1) -> int:
        """Decrement a counter by *amount*."""
        return self._client.decrby(self._key(key), amount)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying Valkey connection."""
        if self._client:
            self._client.close()
            self._client = None