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
        return asyncio.get_event_loop().run_until_complete(self.async_get(key))
    
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
        return asyncio.get_event_loop().run_until_complete(self.async_set(key, value, ttl))
    
    async def async_delete(self, key: str) -> bool:
        """Delete state by key asynchronously."""
        if not self._initialized:
            await self.init()
        
        result = await self._collection.delete_one({"_id": key})
        return result.deleted_count > 0
    
    def delete(self, key: str) -> bool:
        """Sync wrapper for delete."""
        return asyncio.get_event_loop().run_until_complete(self.async_delete(key))
    
    async def async_exists(self, key: str) -> bool:
        """Check if key exists asynchronously."""
        if not self._initialized:
            await self.init()
        
        count = await self._collection.count_documents({"_id": key}, limit=1)
        return count > 0
    
    def exists(self, key: str) -> bool:
        """Sync wrapper for exists."""
        return asyncio.get_event_loop().run_until_complete(self.async_exists(key))
    
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
        return asyncio.get_event_loop().run_until_complete(self.async_list_keys(prefix))
    
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
        return asyncio.get_event_loop().run_until_complete(self.async_clear(prefix))
    
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
            asyncio.get_event_loop().run_until_complete(self.async_close())
