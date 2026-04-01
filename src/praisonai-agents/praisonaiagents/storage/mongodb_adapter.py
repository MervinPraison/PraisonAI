"""
MongoDB Storage Adapter for PraisonAI Agents.

Provides MongoDB-based storage implementation following StorageBackendProtocol.
Uses lazy imports for the optional pymongo dependency.

Example:
    ```python
    from praisonaiagents.storage import MongoDBStorageAdapter
    
    adapter = MongoDBStorageAdapter(url="mongodb://localhost:27017/")
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    ```
"""

import json
import time
import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class MongoDBStorageAdapter:
    """
    MongoDB-based storage adapter implementing StorageBackendProtocol.
    
    Uses MongoDB for document-oriented data storage.
    Requires the `pymongo` package (optional dependency).
    Thread-safe with connection pooling and auto-indexing.
    """
    
    def __init__(
        self,
        url: str = "mongodb://localhost:27017/",
        database: str = "praisonai",
        collection: str = "praison_storage",
        max_pool_size: int = 50,
        timeout_ms: int = 5000,
    ):
        """
        Initialize the MongoDB storage adapter.
        
        Args:
            url: MongoDB connection URL
            database: Database name
            collection: Collection name for storage
            max_pool_size: Maximum connections in pool
            timeout_ms: Connection timeout in milliseconds
        """
        self.url = url
        self.database_name = database
        self.collection_name = collection
        self.max_pool_size = max_pool_size
        self.timeout_ms = timeout_ms
        self._client = None
        self._collection = None
        self._lock = threading.Lock()
    
    def _get_collection(self):
        """Lazy initialize MongoDB client and collection with indexing."""
        if self._collection is None:
            with self._lock:
                if self._collection is None:  # Double-check locking
                    try:
                        import pymongo
                    except ImportError:
                        raise ImportError(
                            "MongoDB storage adapter requires the 'pymongo' package. "
                            "Install with: pip install praisonaiagents[mongodb]"
                        )
                    
                    # Create client with connection pooling
                    self._client = pymongo.MongoClient(
                        self.url,
                        maxPoolSize=self.max_pool_size,
                        retryWrites=True,
                        retryReads=True,
                        serverSelectionTimeoutMS=self.timeout_ms,
                        connectTimeoutMS=self.timeout_ms,
                    )
                    
                    # Test connection
                    try:
                        self._client.admin.command('ping')
                        logger.info(f"Connected to MongoDB at {self.url}")
                    except Exception as e:
                        logger.error(f"Failed to connect to MongoDB: {e}")
                        raise
                    
                    db = self._client[self.database_name]
                    self._collection = db[self.collection_name]
                    
                    # Create index for better performance on prefix queries
                    try:
                        self._collection.create_index([("_id", 1)], background=True)
                        self._collection.create_index([("updated_at", -1)], background=True)
                    except Exception as e:
                        logger.warning(f"Failed to create MongoDB indexes: {e}")
        
        return self._collection
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key (upsert operation)."""
        try:
            collection = self._get_collection()
            json_data = json.dumps(data, default=str, ensure_ascii=False)
            
            result = collection.replace_one(
                {"_id": key},
                {
                    "_id": key,
                    "data": json_data,
                    "updated_at": time.time(),
                    "created_at": time.time()  # Only set on insert
                },
                upsert=True
            )
            
            logger.debug(f"{'Updated' if result.matched_count else 'Created'} MongoDB document: {key}")
        except Exception as e:
            logger.error(f"Failed to save data to MongoDB key {key}: {e}")
            raise
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        try:
            collection = self._get_collection()
            doc = collection.find_one({"_id": key})
            
            if doc and "data" in doc:
                try:
                    return json.loads(doc["data"])
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode JSON for key {key}: {e}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to load data from MongoDB key {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        try:
            collection = self._get_collection()
            result = collection.delete_one({"_id": key})
            
            if result.deleted_count > 0:
                logger.debug(f"Deleted MongoDB document: {key}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete MongoDB key {key}: {e}")
            return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        try:
            collection = self._get_collection()
            
            if prefix:
                # Use regex for prefix matching with proper escaping
                import re
                escaped_prefix = re.escape(prefix)
                cursor = collection.find(
                    {"_id": {"$regex": f"^{escaped_prefix}"}},
                    {"_id": 1}
                ).sort("_id", 1)
            else:
                cursor = collection.find({}, {"_id": 1}).sort("_id", 1)
            
            return [doc["_id"] for doc in cursor]
        except Exception as e:
            logger.error(f"Failed to list MongoDB keys: {e}")
            return []
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        try:
            collection = self._get_collection()
            return collection.count_documents({"_id": key}, limit=1) > 0
        except Exception as e:
            logger.error(f"Failed to check existence of MongoDB key {key}: {e}")
            return False
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        try:
            collection = self._get_collection()
            result = collection.delete_many({})
            count = result.deleted_count
            logger.info(f"Cleared {count} documents from MongoDB")
            return count
        except Exception as e:
            logger.error(f"Failed to clear MongoDB data: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            collection = self._get_collection()
            stats = collection.estimated_document_count()
            return {
                "document_count": stats,
                "database": self.database_name,
                "collection": self.collection_name
            }
        except Exception as e:
            logger.error(f"Failed to get MongoDB stats: {e}")
            return {}
    
    def cleanup_old_documents(self, max_age_seconds: int = 2592000) -> int:
        """
        Delete documents older than specified age.
        
        Args:
            max_age_seconds: Maximum age in seconds (default: 30 days)
            
        Returns:
            Number of deleted documents
        """
        try:
            collection = self._get_collection()
            cutoff_time = time.time() - max_age_seconds
            
            result = collection.delete_many({"updated_at": {"$lt": cutoff_time}})
            count = result.deleted_count
            
            if count > 0:
                logger.info(f"Cleaned up {count} old MongoDB documents")
            
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup old MongoDB documents: {e}")
            return 0
    
    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            try:
                self._client.close()
                logger.debug("Closed MongoDB connection")
            except Exception as e:
                logger.warning(f"Error closing MongoDB connection: {e}")
            finally:
                self._client = None
                self._collection = None


__all__ = ['MongoDBStorageAdapter']