"""
Valkey implementation of StateStore.

Requires: valkey-glide-sync
Install: pip install 'praisonai[valkey]'
"""

import json
from typing import Any, Dict, List, Optional

from .base import StateStore
from .._valkey_client import create_valkey_client

try:
    from glide_sync import ExpirySet, ExpiryType
except ImportError:
    ExpirySet = None
    ExpiryType = None


class ValkeyStateStore(StateStore):
    """
    Valkey-based state store for fast key-value operations.

    Example:
        store = ValkeyStateStore(
            host="localhost",
            port=6379,
        )
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        prefix: str = "praison:",
        db: int = 0,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.prefix = prefix
        self.db = db
        self._client = None

    def _get_client(self):
        """Lazy initialize Valkey client."""
        if self._client is None:
            self._client = create_valkey_client(
                host=self.host,
                port=self.port,
                password=self.password,
                db=self.db,
            )
        return self._client

    def _key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.prefix}{key}"

    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        client = self._get_client()
        try:
            value = client.get(self._key(key))
        except Exception as e:
            raise RuntimeError(f"Failed to get key from Valkey: {e}") from e

        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode()
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set a value with optional TTL."""
        client = self._get_client()
        if not isinstance(value, str):
            value = json.dumps(value)

        try:
            if ttl is not None:
                client.set(self._key(key), value, expiry=ExpirySet(ExpiryType.SEC, ttl))
            else:
                client.set(self._key(key), value)
        except Exception as e:
            raise RuntimeError(f"Failed to set key in Valkey: {e}") from e

    def delete(self, key: str) -> bool:
        """Delete a key."""
        client = self._get_client()
        try:
            return client.delete([self._key(key)]) > 0
        except Exception as e:
            raise RuntimeError(f"Failed to delete key from Valkey: {e}") from e

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        client = self._get_client()
        try:
            return client.exists([self._key(key)]) > 0
        except Exception as e:
            raise RuntimeError(f"Failed to check key existence in Valkey: {e}") from e

    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        client = self._get_client()
        full_pattern = self._key(pattern)
        try:
            cursor: bytes = b"0"
            all_keys = []
            while True:
                result = client.scan(cursor, match=full_pattern, count=100)
                cursor = result[0]
                all_keys.extend(result[1] or [])
                if not cursor or cursor in (b"0", "0"):
                    break
            prefix_len = len(self.prefix)
            result_keys = []
            for k in all_keys:
                k_str = k.decode() if isinstance(k, bytes) else k
                result_keys.append(k_str[prefix_len:] if k_str.startswith(self.prefix) else k_str)
            return result_keys
        except Exception as e:
            raise RuntimeError(f"Failed to list keys from Valkey: {e}") from e

    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds."""
        client = self._get_client()
        try:
            result = client.ttl(self._key(key))
        except Exception as e:
            raise RuntimeError(f"Failed to get TTL from Valkey: {e}") from e

        if result is None or result < 0:
            return None
        return int(result)

    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        client = self._get_client()
        try:
            return bool(client.expire(self._key(key), ttl))
        except Exception as e:
            raise RuntimeError(f"Failed to set expire in Valkey: {e}") from e

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        client = self._get_client()
        try:
            value = client.hget(self._key(key), field)
        except Exception as e:
            raise RuntimeError(f"Failed to hget from Valkey: {e}") from e

        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode()
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash."""
        client = self._get_client()
        if not isinstance(value, str):
            value = json.dumps(value)
        try:
            client.hset(self._key(key), {field: value})
        except Exception as e:
            raise RuntimeError(f"Failed to hset in Valkey: {e}") from e

    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        client = self._get_client()
        try:
            data = client.hgetall(self._key(key))
        except Exception as e:
            raise RuntimeError(f"Failed to hgetall from Valkey: {e}") from e

        result = {}
        if not data:
            return result
        for k, v in data.items():
            k_str = k.decode() if isinstance(k, bytes) else k
            v_str = v.decode() if isinstance(v, bytes) else v
            try:
                result[k_str] = json.loads(v_str)
            except (json.JSONDecodeError, TypeError):
                result[k_str] = v_str
        return result

    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash."""
        if not fields:
            return 0
        client = self._get_client()
        try:
            return client.hdel(self._key(key), list(fields))
        except Exception as e:
            raise RuntimeError(f"Failed to hdel from Valkey: {e}") from e

    def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter."""
        client = self._get_client()
        try:
            return client.incrby(self._key(key), amount)
        except Exception as e:
            raise RuntimeError(f"Failed to increment key in Valkey: {e}") from e

    def decr(self, key: str, amount: int = 1) -> int:
        """Decrement a counter."""
        client = self._get_client()
        try:
            return client.decrby(self._key(key), amount)
        except Exception as e:
            raise RuntimeError(f"Failed to decrement key in Valkey: {e}") from e

    def close(self) -> None:
        """Close the store."""
        if self._client:
            try:
                self._client.close()
            finally:
                self._client = None
