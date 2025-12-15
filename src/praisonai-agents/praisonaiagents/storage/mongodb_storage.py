"""
MongoDB storage backend for PraisonAI Agents.

This module provides MongoDB-based storage implementation with full NoSQL capabilities.
"""

import time
import asyncio
from typing import Any, Dict, List, Optional
from .base import BaseStorage

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import ASCENDING, DESCENDING, TEXT
    from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    AsyncIOMotorClient = None


class MongoDBStorage(BaseStorage):
    """
    MongoDB storage backend implementation.
    
    Provides scalable NoSQL storage with full-text search, indexing,
    and automatic expiration support.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MongoDB storage.
        
        Args:
            config: Configuration dictionary with keys:
                - url: MongoDB connection URL (default: "mongodb://localhost:27017/")
                - database: Database name (default: "praisonai")
                - collection: Collection name (default: "agent_memory")
                - indexes: List of fields to index (default: ["created_at", "updated_at"])
                - ttl_field: Field name for TTL expiration (optional)
                - ttl_seconds: TTL expiration time in seconds (default: None)
                - timeout: Connection timeout in ms (default: 5000)
        """
        if not MONGODB_AVAILABLE:
            raise ImportError(
                "MongoDB storage requires motor and pymongo. "
                "Install with: pip install motor pymongo"
            )
        
        super().__init__(config)
        
        self.url = config.get("url", "mongodb://localhost:27017/")
        self.database_name = config.get("database", "praisonai")
        self.collection_name = config.get("collection", "agent_memory")
        self.indexes = config.get("indexes", ["created_at", "updated_at"])
        self.ttl_field = config.get("ttl_field")
        self.ttl_seconds = config.get("ttl_seconds")
        self.timeout = config.get("timeout", 5000)
        
        # Connection will be initialized on first use
        self.client = None
        self.database = None
        self.collection = None
        self._initialized = False
    
    async def _ensure_connection(self):
        """Ensure MongoDB connection is established."""
        if not self._initialized:
            try:
                self.client = AsyncIOMotorClient(
                    self.url,
                    serverSelectionTimeoutMS=self.timeout
                )
                
                # Test connection
                await self.client.admin.command('ping')
                
                self.database = self.client[self.database_name]
                self.collection = self.database[self.collection_name]
                
                # Create indexes
                await self._create_indexes()
                
                self._initialized = True
                self.logger.info(f"Connected to MongoDB: {self.database_name}.{self.collection_name}")
                
            except ServerSelectionTimeoutError as e:
                self.logger.error(f"Failed to connect to MongoDB: {e}")
                raise
            except Exception as e:
                self.logger.error(f"Unexpected error connecting to MongoDB: {e}")
                raise
    
    async def _create_indexes(self):
        """Create indexes for better performance."""
        try:
            # Create basic indexes
            for field in self.indexes:
                await self.collection.create_index([(field, ASCENDING)])
            
            # Create text index for full-text search on content
            await self.collection.create_index([("content", TEXT)])
            
            # Create TTL index if configured
            if self.ttl_field and self.ttl_seconds:
                await self.collection.create_index(
                    [(self.ttl_field, ASCENDING)],
                    expireAfterSeconds=self.ttl_seconds
                )
            
            self.logger.info("MongoDB indexes created successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to create MongoDB indexes: {e}")
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        await self._ensure_connection()
        
        try:
            doc = await self.collection.find_one({"_id": key})
            if doc:
                # Convert MongoDB _id to id for consistency
                doc["id"] = doc.pop("_id")
                return doc
            return None
        except Exception as e:
            self.logger.error(f"Failed to read key {key}: {e}")
            return None
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        await self._ensure_connection()
        
        try:
            # Prepare document
            doc = data.copy()
            doc["_id"] = key
            doc["updated_at"] = time.time()
            
            # Set created_at if not present
            if "created_at" not in doc:
                doc["created_at"] = doc["updated_at"]
            
            # Set TTL field if configured
            if self.ttl_field and self.ttl_field not in doc:
                doc[self.ttl_field] = time.time()
            
            # Use upsert for atomic update or insert
            await self.collection.replace_one(
                {"_id": key},
                doc,
                upsert=True
            )
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to write key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        await self._ensure_connection()
        
        try:
            result = await self.collection.delete_one({"_id": key})
            return result.deleted_count > 0
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for records matching the query."""
        await self._ensure_connection()
        
        try:
            # Build MongoDB query
            mongo_query = {}
            
            # Text search
            if "text" in query:
                mongo_query["$text"] = {"$search": query["text"]}
            
            # Metadata search
            if "metadata" in query:
                for key, value in query["metadata"].items():
                    mongo_query[f"metadata.{key}"] = value
            
            # Time range filters
            if "created_after" in query or "created_before" in query:
                mongo_query["created_at"] = {}
                if "created_after" in query:
                    mongo_query["created_at"]["$gte"] = query["created_after"]
                if "created_before" in query:
                    mongo_query["created_at"]["$lte"] = query["created_before"]
            
            # Execute query with limit and sorting
            limit = query.get("limit", 100)
            cursor = self.collection.find(mongo_query).limit(limit)
            
            # Sort by relevance score if text search, otherwise by updated_at
            if "$text" in mongo_query:
                cursor = cursor.sort([("score", {"$meta": "textScore"})])
            else:
                cursor = cursor.sort("updated_at", DESCENDING)
            
            # Convert results
            results = []
            async for doc in cursor:
                doc["id"] = doc.pop("_id")
                results.append(doc)
            
            return results
        except Exception as e:
            self.logger.error(f"Failed to search: {e}")
            return []
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        await self._ensure_connection()
        
        try:
            # Build query for prefix filtering
            query = {}
            if prefix:
                query["_id"] = {"$regex": f"^{prefix}"}
            
            # Get only the _id field
            cursor = self.collection.find(query, {"_id": 1})
            
            if limit:
                cursor = cursor.limit(limit)
            
            cursor = cursor.sort("created_at", DESCENDING)
            
            keys = []
            async for doc in cursor:
                keys.append(doc["_id"])
            
            return keys
        except Exception as e:
            self.logger.error(f"Failed to list keys: {e}")
            return []
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        await self._ensure_connection()
        
        try:
            await self.collection.delete_many({})
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
    
    async def batch_write(self, records: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Optimized batch write for MongoDB."""
        await self._ensure_connection()
        
        results = {}
        
        try:
            # Prepare bulk operations
            operations = []
            current_time = time.time()
            
            for key, data in records.items():
                doc = data.copy()
                doc["_id"] = key
                doc["updated_at"] = current_time
                
                if "created_at" not in doc:
                    doc["created_at"] = current_time
                
                if self.ttl_field and self.ttl_field not in doc:
                    doc[self.ttl_field] = current_time
                
                operations.append({
                    "replaceOne": {
                        "filter": {"_id": key},
                        "replacement": doc,
                        "upsert": True
                    }
                })
            
            # Execute bulk operation
            if operations:
                result = await self.collection.bulk_write(operations)
                
                # Mark all as successful if bulk operation succeeded
                for key in records.keys():
                    results[key] = True
            
        except Exception as e:
            self.logger.error(f"Failed batch write: {e}")
            for key in records.keys():
                results[key] = False
        
        return results
    
    async def batch_read(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Optimized batch read for MongoDB."""
        await self._ensure_connection()
        
        results = {key: None for key in keys}
        
        try:
            cursor = self.collection.find({"_id": {"$in": keys}})
            
            async for doc in cursor:
                key = doc.pop("_id")
                doc["id"] = key
                results[key] = doc
                
        except Exception as e:
            self.logger.error(f"Failed batch read: {e}")
        
        return results
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        await self._ensure_connection()
        
        try:
            count = await self.collection.count_documents({"_id": key}, limit=1)
            return count > 0
        except Exception as e:
            self.logger.error(f"Failed to check existence of key {key}: {e}")
            return False
    
    async def count(self) -> int:
        """Count total number of records in storage."""
        await self._ensure_connection()
        
        try:
            return await self.collection.count_documents({})
        except Exception as e:
            self.logger.error(f"Failed to count records: {e}")
            return 0
    
    async def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self._initialized = False