"""
Firestore implementation of StateStore.

Requires: google-cloud-firestore
Install: pip install google-cloud-firestore
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


class FirestoreStateStore(StateStore):
    """
    Firestore-based state store.
    
    Example:
        store = FirestoreStateStore(
            project="my-project",
            collection="praisonai_state"
        )
    """
    
    def __init__(
        self,
        project: Optional[str] = None,
        collection: str = "praisonai_state",
        credentials_path: Optional[str] = None,
    ):
        try:
            from google.cloud import firestore
        except ImportError:
            raise ImportError(
                "google-cloud-firestore is required for Firestore support. "
                "Install with: pip install google-cloud-firestore"
            )
        
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
        
        project = project or os.getenv("FIRESTORE_PROJECT")
        self._client = firestore.Client(project=project)
        self._collection = self._client.collection(collection)
        
        logger.info(f"Connected to Firestore collection: {collection}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        doc = self._collection.document(key).get()
        if not doc.exists:
            return None
        
        data = doc.to_dict()
        
        # Check TTL
        if data.get("expires_at") and data["expires_at"] <= time.time():
            self._collection.document(key).delete()
            return None
        
        return data.get("value")
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set a value with optional TTL."""
        data = {"value": value, "updated_at": time.time()}
        
        if ttl:
            data["expires_at"] = time.time() + ttl
        
        self._collection.document(key).set(data)
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        doc = self._collection.document(key)
        if doc.get().exists:
            doc.delete()
            return True
        return False
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        doc = self._collection.document(key).get()
        if not doc.exists:
            return False
        
        data = doc.to_dict()
        if data.get("expires_at") and data["expires_at"] <= time.time():
            return False
        
        return True
    
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        docs = self._collection.stream()
        keys = [doc.id for doc in docs]
        
        if pattern != "*":
            import fnmatch
            keys = [k for k in keys if fnmatch.fnmatch(k, pattern)]
        
        return keys
    
    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds."""
        doc = self._collection.document(key).get()
        if not doc.exists:
            return None
        
        data = doc.to_dict()
        if "expires_at" not in data:
            return None
        
        remaining = data["expires_at"] - time.time()
        if remaining <= 0:
            return None
        return int(remaining)
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        doc = self._collection.document(key)
        if not doc.get().exists:
            return False
        
        doc.update({"expires_at": time.time() + ttl})
        return True
    
    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        value = self.get(key)
        if not isinstance(value, dict):
            return None
        return value.get(field)
    
    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash."""
        current = self.get(key)
        if not isinstance(current, dict):
            current = {}
        current[field] = value
        self.set(key, current)
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        value = self.get(key)
        if not isinstance(value, dict):
            return {}
        return value
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash."""
        current = self.get(key)
        if not isinstance(current, dict):
            return 0
        count = 0
        for field in fields:
            if field in current:
                del current[field]
                count += 1
        if count > 0:
            self.set(key, current)
        return count
    
    def close(self) -> None:
        """Close the store."""
        pass  # Firestore client handles cleanup
