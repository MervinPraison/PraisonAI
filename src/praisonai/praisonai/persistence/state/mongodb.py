"""
MongoDB implementation of StateStore.

Requires: pymongo
Install: pip install pymongo
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .base import StateStore

logger = logging.getLogger(__name__)


class MongoDBStateStore(StateStore):
    """
    MongoDB-based state store.
    
    Example:
        store = MongoDBStateStore(
            url="mongodb://localhost:27017",
            database="praisonai"
        )
    """
    
    def __init__(
        self,
        url: str = "mongodb://localhost:27017",
        database: str = "praisonai",
        collection: str = "state",
    ):
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ImportError(
                "pymongo is required for MongoDB support. "
                "Install with: pip install pymongo"
            )
        
        self._client = MongoClient(url)
        self._db = self._client[database]
        self._collection = self._db[collection]
        
        # Create TTL index for automatic expiration
        self._collection.create_index("expires_at", expireAfterSeconds=0)
        
        logger.info(f"Connected to MongoDB: {database}.{collection}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key."""
        doc = self._collection.find_one({"_id": key})
        if not doc:
            return None
        
        # Check TTL
        if doc.get("expires_at") and doc["expires_at"] <= time.time():
            self._collection.delete_one({"_id": key})
            return None
        
        return doc.get("value")
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """Set a value with optional TTL."""
        doc = {"_id": key, "value": value, "updated_at": time.time()}
        
        if ttl:
            from datetime import datetime, timedelta
            doc["expires_at"] = datetime.utcnow() + timedelta(seconds=ttl)
        
        self._collection.replace_one({"_id": key}, doc, upsert=True)
    
    def delete(self, key: str) -> bool:
        """Delete a key."""
        result = self._collection.delete_one({"_id": key})
        return result.deleted_count > 0
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        doc = self._collection.find_one({"_id": key}, {"_id": 1, "expires_at": 1})
        if not doc:
            return False
        if doc.get("expires_at") and doc["expires_at"] <= time.time():
            return False
        return True
    
    def keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        if pattern == "*":
            cursor = self._collection.find({}, {"_id": 1})
        else:
            # Convert glob pattern to regex
            import re
            regex = pattern.replace("*", ".*").replace("?", ".")
            cursor = self._collection.find({"_id": {"$regex": f"^{regex}$"}}, {"_id": 1})
        
        return [doc["_id"] for doc in cursor]
    
    def ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds."""
        doc = self._collection.find_one({"_id": key}, {"expires_at": 1})
        if not doc or "expires_at" not in doc:
            return None
        
        remaining = doc["expires_at"].timestamp() - time.time()
        if remaining <= 0:
            return None
        return int(remaining)
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        from datetime import datetime, timedelta
        
        result = self._collection.update_one(
            {"_id": key},
            {"$set": {"expires_at": datetime.utcnow() + timedelta(seconds=ttl)}}
        )
        return result.modified_count > 0
    
    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash."""
        doc = self._collection.find_one({"_id": key})
        if not doc or not isinstance(doc.get("value"), dict):
            return None
        return doc["value"].get(field)
    
    def hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash."""
        self._collection.update_one(
            {"_id": key},
            {"$set": {f"value.{field}": value, "updated_at": time.time()}},
            upsert=True
        )
    
    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash."""
        doc = self._collection.find_one({"_id": key})
        if not doc or not isinstance(doc.get("value"), dict):
            return {}
        return doc["value"]
    
    def hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash."""
        unset = {f"value.{field}": "" for field in fields}
        result = self._collection.update_one({"_id": key}, {"$unset": unset})
        return len(fields) if result.modified_count > 0 else 0
    
    def close(self) -> None:
        """Close the store."""
        if self._client:
            self._client.close()
