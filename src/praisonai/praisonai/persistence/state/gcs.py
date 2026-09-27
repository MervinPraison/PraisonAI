"""
Google Cloud Storage implementation of StateStore.

Requires: google-cloud-storage
Install: pip install google-cloud-storage
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


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
    
    def get(self, key: str) -> Optional[Any]:
        """Get state by key."""
        try:
            blob = self._bucket.blob(self._key_to_path(key))
            if blob.exists():
                data = json.loads(blob.download_as_text())
                # Check TTL
                if "_ttl_expires" in data:
                    if time.time() > data["_ttl_expires"]:
                        self.delete(key)
                        return None
                    del data["_ttl_expires"]
                # Unwrap scalars stored via set() so values round-trip.
                if isinstance(data, dict) and set(data.keys()) == {"__value__"}:
                    return data["__value__"]
                return data
            return None
        except Exception as e:
            logger.error(f"Error getting state {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set state by key with optional TTL in seconds.

        Non-dict values are wrapped so any JSON-native value round-trips
        through :meth:`get`, matching the ``StateStore.set`` contract.
        """
        try:
            if isinstance(value, dict):
                data = value.copy()
            else:
                data = {"__value__": value}
            if ttl:
                data["_ttl_expires"] = time.time() + ttl

            blob = self._bucket.blob(self._key_to_path(key))
            blob.upload_from_string(
                json.dumps(data, default=str),
                content_type="application/json"
            )
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
            blob = self._bucket.blob(self._key_to_path(key))
            if not blob.exists():
                return None
            raw = json.loads(blob.download_as_text())
        except Exception as e:
            logger.error(f"Error reading TTL for {key}: {e}")
            return None
        expires = raw.get("_ttl_expires") if isinstance(raw, dict) else None
        if expires is None:
            return None
        remaining = int(expires - time.time())
        return remaining if remaining > 0 else None

    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on an existing key. Returns True if the key exists."""
        data = self.get(key)
        if data is None:
            return False
        self.set(key, data, ttl=ttl)
        return True

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash stored at ``key``."""
        data = self.get(key)
        if not isinstance(data, dict):
            return None
        return data.get(field)

    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash stored at ``key``."""
        data = self.get(key)
        if not isinstance(data, dict):
            data = {}
        data[field] = value
        self.set(key, data)

    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash stored at ``key``."""
        data = self.get(key)
        return dict(data) if isinstance(data, dict) else {}

    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash. Returns count deleted."""
        data = self.get(key)
        if not isinstance(data, dict):
            return 0
        count = 0
        for field in fields:
            if field in data:
                del data[field]
                count += 1
        if count:
            self.set(key, data)
        return count

    def close(self) -> None:
        """Close the store."""
        self._client.close()
