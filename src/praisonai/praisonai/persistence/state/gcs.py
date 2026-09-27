"""
Google Cloud Storage implementation of StateStore.

Requires: google-cloud-storage
Install: pip install google-cloud-storage
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .base import StateStore

logger = logging.getLogger(__name__)

# Sentinel key used to wrap non-dict scalars so any JSON-native value can
# round-trip through get()/set(). A caller-supplied dict is only treated as a
# wrapper when it also carries this marker, so a legitimate ``{"__value__": 42}``
# payload is preserved instead of being silently unwrapped.
_SCALAR_VALUE = "__value__"
_SCALAR_MARKER = "__praisonai_scalar__"


class GCSStateStore(StateStore):
    """
    Google Cloud Storage-based state store.
    
    Stores state as JSON objects in GCS buckets.
    
    Example:
        store = GCSStateStore(
            bucket_name="my-praisonai-state",
            prefix="state/"
        )
    """
    
    def __init__(
        self,
        bucket_name: str,
        prefix: str = "praisonai_state/",
        project: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ):
        """
        Initialize GCS state store.
        
        Args:
            bucket_name: GCS bucket name
            prefix: Object prefix for state keys
            project: GCP project ID (optional)
            credentials_path: Path to service account JSON (optional)
        """
        try:
            from google.cloud import storage
            if credentials_path:
                self._client = storage.Client.from_service_account_json(
                    credentials_path, project=project
                )
            else:
                self._client = storage.Client(project=project)
        except ImportError:
            raise ImportError(
                "google-cloud-storage is required for GCS support. "
                "Install with: pip install google-cloud-storage"
            )
        
        self.bucket_name = bucket_name
        self.prefix = prefix
        self._bucket = self._client.bucket(bucket_name)
    
    def _key_to_path(self, key: str) -> str:
        """Convert key to GCS object path."""
        return f"{self.prefix}{key}.json"
    
    def _read_raw(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the raw stored envelope (incl. ``_ttl_expires``), or None.

        Applies TTL expiry (deleting the key) but does NOT unwrap scalars, so
        hash/TTL helpers can preserve the existing expiry when rewriting.
        """
        blob = self._bucket.blob(self._key_to_path(key))
        if not blob.exists():
            return None
        data = json.loads(blob.download_as_text())
        if isinstance(data, dict) and "_ttl_expires" in data:
            if time.time() > data["_ttl_expires"]:
                self.delete(key)
                return None
        return data

    def get(self, key: str) -> Optional[Any]:
        """Get state by key."""
        try:
            data = self._read_raw(key)
            if data is None:
                return None
            if isinstance(data, dict):
                data = dict(data)
                data.pop("_ttl_expires", None)
                # Unwrap scalars stored via set() so values round-trip. Only a
                # dict carrying the private marker is a wrapper; a caller's own
                # ``{"__value__": ...}`` dict is left intact.
                if data.get(_SCALAR_MARKER) is True and _SCALAR_VALUE in data:
                    return data[_SCALAR_VALUE]
            return data
        except Exception as e:
            logger.error(f"Error getting state {key}: {e}")
            return None
    
    def _write_envelope(self, key: str, value: Any, ttl_expires: Optional[float]) -> bool:
        """Serialise + upload an envelope. Returns True on success.

        ``value`` is a scalar or dict; scalars/marker-shaped dicts are wrapped so
        they round-trip. ``ttl_expires`` is an absolute epoch time (or None).
        """
        if isinstance(value, dict) and value.get(_SCALAR_MARKER) is not True:
            data = dict(value)
        else:
            data = {_SCALAR_MARKER: True, _SCALAR_VALUE: value}
        if ttl_expires is not None:
            data["_ttl_expires"] = ttl_expires
        blob = self._bucket.blob(self._key_to_path(key))
        blob.upload_from_string(
            json.dumps(data, default=str),
            content_type="application/json",
        )
        return True

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set state by key with optional TTL in seconds.

        Non-dict values are wrapped so any JSON-native value round-trips
        through :meth:`get`, matching the ``StateStore.set`` contract.
        """
        try:
            ttl_expires = time.time() + ttl if ttl else None
            self._write_envelope(key, value, ttl_expires)
        except Exception as e:
            logger.error(f"Error setting state {key}: {e}")
    
    def delete(self, key: str) -> bool:
        """Delete state by key."""
        try:
            blob = self._bucket.blob(self._key_to_path(key))
            if blob.exists():
                blob.delete()
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting state {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            blob = self._bucket.blob(self._key_to_path(key))
            return blob.exists()
        except Exception:
            return False
    
    def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """List all keys with optional prefix filter."""
        try:
            search_prefix = self.prefix
            if prefix:
                search_prefix = f"{self.prefix}{prefix}"
            
            blobs = self._client.list_blobs(self.bucket_name, prefix=search_prefix)
            keys = []
            for blob in blobs:
                # Remove prefix and .json suffix
                key = blob.name[len(self.prefix):]
                if key.endswith(".json"):
                    key = key[:-5]
                keys.append(key)
            return keys
        except Exception as e:
            logger.error(f"Error listing keys: {e}")
            return []
    
    def clear(self, prefix: Optional[str] = None) -> int:
        """Clear all keys with optional prefix filter."""
        keys = self.list_keys(prefix)
        count = 0
        for key in keys:
            if self.delete(key):
                count += 1
        return count
    
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching a glob pattern (StateStore contract)."""
        all_keys = self.list_keys()
        if pattern == "*":
            return all_keys
        import fnmatch
        return [k for k in all_keys if fnmatch.fnmatch(k, pattern)]

    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds. Returns None if no TTL or missing."""
        try:
            raw = self._read_raw(key)
        except Exception as e:
            logger.error(f"Error reading TTL for {key}: {e}")
            return None
        expires = raw.get("_ttl_expires") if isinstance(raw, dict) else None
        if expires is None:
            return None
        remaining = int(expires - time.time())
        return remaining if remaining > 0 else None

    def _read_hash(self, key: str) -> Tuple[Dict[str, Any], Optional[float]]:
        """Return (fields, ttl_expires) for a hash, dropping the private markers."""
        raw = self._read_raw(key)
        if not isinstance(raw, dict):
            return {}, None
        ttl_expires = raw.get("_ttl_expires")
        fields = {
            k: v
            for k, v in raw.items()
            if k not in ("_ttl_expires", _SCALAR_MARKER, _SCALAR_VALUE)
        }
        return fields, ttl_expires

    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on an existing key. Returns True only if the write succeeds."""
        raw = self._read_raw(key)
        if raw is None:
            return False
        # Preserve the stored envelope shape (scalar wrapper or dict) verbatim,
        # only refreshing the expiry, and honour the actual upload result so a
        # failed GCS write is not reported as success.
        payload = raw if isinstance(raw, dict) else {_SCALAR_MARKER: True, _SCALAR_VALUE: raw}
        try:
            return self._write_envelope(
                key,
                {k: v for k, v in payload.items() if k != "_ttl_expires"},
                time.time() + ttl,
            )
        except Exception as e:
            logger.error(f"Error setting TTL for {key}: {e}")
            return False

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash stored at ``key``."""
        fields, _ = self._read_hash(key)
        return fields.get(field)

    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash stored at ``key``, preserving any existing TTL.

        Note: GCS objects are whole-blob; a hash is stored as one JSON object,
        so field updates are read-modify-write rather than field-atomic. For
        high-contention field-level concurrency prefer a document store
        (Firestore) or Redis. TTL is carried over so it is not reset here.
        """
        fields, ttl_expires = self._read_hash(key)
        fields[field] = value
        try:
            self._write_envelope(key, fields, ttl_expires)
        except Exception as e:
            logger.error(f"Error setting hash field {key}.{field}: {e}")

    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash stored at ``key``."""
        fields, _ = self._read_hash(key)
        return fields

    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash, preserving any existing TTL.

        Returns the number of fields actually removed. If the rewrite fails the
        deletion is reported as 0 rather than falsely claiming success.
        """
        stored, ttl_expires = self._read_hash(key)
        present = [f for f in fields if f in stored]
        if not present:
            return 0
        for field in present:
            del stored[field]
        try:
            self._write_envelope(key, stored, ttl_expires)
        except Exception as e:
            logger.error(f"Error deleting hash fields from {key}: {e}")
            return 0
        return len(present)

    def close(self) -> None:
        """Close the store."""
        self._client.close()
