"""
Async MongoDB implementation of StateStore.

Requires: motor
Install: pip install motor
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .base import StateStore
# Route sync wrappers through run_sync_or_offload so these methods are safe
# from inside a running loop (FastAPI handler, async test, notebook). A bare
# run_sync would raise RuntimeError there, making sync persistence hooks that
# ride an async store unusable in exactly the environments they target.
from ..._async_bridge import run_sync_or_offload as run_sync

logger = logging.getLogger(__name__)


class AsyncMongoDBStateStore(StateStore):
    """
    Async MongoDB state store using motor.
    
    Provides high-performance async database operations.
    
    Example:
        store = AsyncMongoDBStateStore(
            url="mongodb://localhost:27017",
            database="praisonai"
        )
        await store.init()
    """
    
    def __init__(
        self,
        url: str = "mongodb://localhost:27017",
        database: str = "praisonai",
        collection: str = "state",
    ):
        """
        Initialize async MongoDB store.
        
        Args:
            url: MongoDB connection URL
            database: Database name
            collection: Collection name
        """
        self.url = url
        self.database_name = database
        self.collection_name = collection
        self._client = None
        self._db = None
        self._collection = None
        self._initialized = False
    
    async def init(self):
        """Initialize connection."""
        if self._initialized:
            return
        
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError:
            raise ImportError(
                "motor is required for async MongoDB support. "
                "Install with: pip install motor"
            )
        
        self._client = AsyncIOMotorClient(self.url)
        self._db = self._client[self.database_name]
        self._collection = self._db[self.collection_name]
        
        # Create TTL index for expiration
        await self._collection.create_index("expires_at", expireAfterSeconds=0)
        
        self._initialized = True
    
    async def async_get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get state by key asynchronously."""
        if not self._initialized:
            await self.init()
        
        doc = await self._collection.find_one({"_id": key})
        if doc:
            # Check TTL manually (in case index hasn't cleaned up yet)
            if "expires_at" in doc and doc["expires_at"]:
                if time.time() > doc["expires_at"]:
                    await self.async_delete(key)
                    return None
            
            # Remove internal fields
            result = dict(doc)
            result.pop("_id", None)
            result.pop("expires_at", None)
            return result.get("value", result)
        return None
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Sync wrapper for get."""
        return run_sync(self.async_get(key))
    
    async def async_set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Set state by key with optional TTL asynchronously."""
        if not self._initialized:
            await self.init()
        
        doc = {
            "_id": key,
            "value": value,
            "updated_at": time.time(),
        }
        
        if ttl:
            doc["expires_at"] = time.time() + ttl
        
        try:
            await self._collection.replace_one(
                {"_id": key},
                doc,
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error setting state {key}: {e}")
            return False
    
    def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Sync wrapper for set."""
        return run_sync(self.async_set(key, value, ttl))
    
    async def async_delete(self, key: str) -> bool:
        """Delete state by key asynchronously."""
        if not self._initialized:
            await self.init()
        
        result = await self._collection.delete_one({"_id": key})
        return result.deleted_count > 0
    
    def delete(self, key: str) -> bool:
        """Sync wrapper for delete."""
        return run_sync(self.async_delete(key))
    
    async def async_exists(self, key: str) -> bool:
        """Check if key exists asynchronously."""
        if not self._initialized:
            await self.init()
        
        count = await self._collection.count_documents({"_id": key}, limit=1)
        return count > 0
    
    def exists(self, key: str) -> bool:
        """Sync wrapper for exists."""
        return run_sync(self.async_exists(key))
    
    async def async_list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """List all keys with optional prefix filter asynchronously."""
        if not self._initialized:
            await self.init()
        
        query = {}
        if prefix:
            query["_id"] = {"$regex": f"^{prefix}"}
        
        cursor = self._collection.find(query, {"_id": 1})
        keys = []
        async for doc in cursor:
            keys.append(doc["_id"])
        return keys
    
    def list_keys(self, prefix: Optional[str] = None) -> List[str]:
        """Sync wrapper for list_keys."""
        return run_sync(self.async_list_keys(prefix))
    
    async def async_clear(self, prefix: Optional[str] = None) -> int:
        """Clear all keys with optional prefix filter asynchronously."""
        if not self._initialized:
            await self.init()
        
        query = {}
        if prefix:
            query["_id"] = {"$regex": f"^{prefix}"}
        
        result = await self._collection.delete_many(query)
        return result.deleted_count
    
    def clear(self, prefix: Optional[str] = None) -> int:
        """Sync wrapper for clear."""
        return run_sync(self.async_clear(prefix))
    
    async def async_keys(self, pattern: str = "*") -> List[str]:
        """List keys matching a glob pattern asynchronously.

        Mirrors the sync ``MongoDBStateStore.keys`` hardening: the literal
        portion is ``re.escape``-d before glob wildcards (``*`` -> ``.*``,
        ``?`` -> ``.``) are re-enabled, so regex metacharacters in a
        user-supplied prefix cannot trigger ReDoS or unintended matches.
        """
        if not self._initialized:
            await self.init()

        if pattern == "*":
            cursor = self._collection.find({}, {"_id": 1})
        else:
            import re
            regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
            cursor = self._collection.find({"_id": {"$regex": f"^{regex}$"}}, {"_id": 1})

        return [doc["_id"] async for doc in cursor]

    def keys(self, pattern: str = "*") -> List[str]:
        """Sync wrapper for keys."""
        return run_sync(self.async_keys(pattern))

    async def async_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL in seconds asynchronously."""
        if not self._initialized:
            await self.init()

        doc = await self._collection.find_one({"_id": key}, {"expires_at": 1})
        if not doc or not doc.get("expires_at"):
            return None

        remaining = doc["expires_at"] - time.time()
        if remaining <= 0:
            return None
        return int(remaining)

    def ttl(self, key: str) -> Optional[int]:
        """Sync wrapper for ttl."""
        return run_sync(self.async_ttl(key))

    async def async_expire(self, key: str, ttl: int) -> bool:
        """Set TTL on an existing key asynchronously."""
        if not self._initialized:
            await self.init()

        result = await self._collection.update_one(
            {"_id": key},
            {"$set": {"expires_at": time.time() + ttl}},
        )
        return result.modified_count > 0

    def expire(self, key: str, ttl: int) -> bool:
        """Sync wrapper for expire."""
        return run_sync(self.async_expire(key, ttl))

    async def async_hget(self, key: str, field: str) -> Optional[Any]:
        """Get a field from a hash asynchronously."""
        if not self._initialized:
            await self.init()

        doc = await self._collection.find_one({"_id": key})
        if not doc or not isinstance(doc.get("value"), dict):
            return None
        return doc["value"].get(field)

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Sync wrapper for hget."""
        return run_sync(self.async_hget(key, field))

    async def async_hset(self, key: str, field: str, value: Any) -> None:
        """Set a field in a hash asynchronously.

        Fields are treated as opaque top-level dictionary keys so a field
        containing a dot (e.g. ``"a.b"``) round-trips through ``hget`` /
        ``hgetall`` instead of being reinterpreted as a nested MongoDB path.
        """
        if not self._initialized:
            await self.init()

        # ``$set`` on ``value.<field>`` would let a dotted field escape into a
        # nested path, so target the whole ``value`` subdocument via a
        # positional-free replacement keyed off the current contents.
        await self._collection.update_one(
            {"_id": key},
            [
                {
                    "$set": {
                        "value": {
                            "$mergeObjects": [
                                {"$ifNull": ["$value", {}]},
                                {field: value},
                            ]
                        },
                        "updated_at": time.time(),
                    }
                }
            ],
            upsert=True,
        )

    def hset(self, key: str, field: str, value: Any) -> None:
        """Sync wrapper for hset."""
        run_sync(self.async_hset(key, field, value))

    async def async_hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash asynchronously."""
        if not self._initialized:
            await self.init()

        doc = await self._collection.find_one({"_id": key})
        if not doc or not isinstance(doc.get("value"), dict):
            return {}
        return doc["value"]

    def hgetall(self, key: str) -> Dict[str, Any]:
        """Sync wrapper for hgetall."""
        return run_sync(self.async_hgetall(key))

    async def async_hdel(self, key: str, *fields: str) -> int:
        """Delete fields from a hash asynchronously.

        Returns the number of fields that were actually present and removed
        (matching the ``StateStore`` contract and the Firestore/DynamoDB
        backends), so deleting a mix of present and absent fields reports only
        the real deletions. Fields are treated as opaque top-level keys, so a
        dotted field written via ``hset`` can be deleted by the same name.
        """
        if not self._initialized:
            await self.init()

        if not fields:
            return 0

        doc = await self._collection.find_one({"_id": key}, {"value": 1})
        current = doc.get("value") if doc else None
        if not isinstance(current, dict):
            return 0

        present = [f for f in fields if f in current]
        if not present:
            return 0

        for field in present:
            current.pop(field, None)

        await self._collection.update_one(
            {"_id": key},
            {"$set": {"value": current, "updated_at": time.time()}},
        )
        return len(present)

    def hdel(self, key: str, *fields: str) -> int:
        """Sync wrapper for hdel."""
        return run_sync(self.async_hdel(key, *fields))

    async def async_close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._collection = None
            self._initialized = False
    
    def close(self) -> None:
        """Sync wrapper for close."""
        if self._client:
            run_sync(self.async_close())
