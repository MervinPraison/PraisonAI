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
        
        project = project or os.getenv("FIRESTORE_PROJECT")
        # Scope credentials to this client instead of mutating the
        # process-wide environment, which would leak one tenant's
        # service account into every other Google Cloud client.
        if credentials_path:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            self._client = firestore.Client(project=project, credentials=creds)
        else:
            self._client = firestore.Client(project=project)
        self._firestore = firestore
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
        """Set a field in a hash.

        Uses Firestore's atomic field-level merge so concurrent writers to
        different fields of the same key do not clobber each other, and any
        existing TTL (``expires_at``) is preserved.
        """
        self._collection.document(key).set(
            {"value": {field: value}, "updated_at": time.time()},
            merge=True,
        )
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        value = self.get(key)
        if not isinstance(value, dict):
            return {}
        return value
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash.

        Uses Firestore's atomic field-level delete so it does not clobber
        concurrent writes to other fields of the same key.
        """
        if not fields:
            return 0
        existing = self.get(key)
        if not isinstance(existing, dict):
            return 0
        present = [f for f in fields if f in existing]
        if not present:
            return 0
        doc = self._collection.document(key)
        updates = {
            f"value.{field}": self._firestore.DELETE_FIELD for field in present
        }
        try:
            doc.update(updates)
            return len(present)
        except Exception:
            return 0
    
    def close(self) -> None:
        """Close the store."""
        pass  # Firestore client handles cleanup
