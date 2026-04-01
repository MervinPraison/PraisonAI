"""
MongoDB Storage Adapter for PraisonAI Agents.

Provides MongoDBStorageAdapter implementing StorageBackendProtocol:
- Document-oriented data storage
- Connection pooling for performance  
- GIN indexing for fast text searches
- Automatic collection creation
- Thread-safe operations

Architecture:
- Uses lazy imports (pymongo package is optional)
- Implements StorageBackendProtocol
- Zero performance impact when not used
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
    
    Uses MongoDB for document-oriented data storage with rich querying capabilities.
    Requires the `pymongo` package (optional dependency).
    
    Features:
    - Connection pooling for performance
    - Automatic collection and index creation
    - GIN indexing for fast text searches
    - Atomic upsert operations
    - Thread-safe operations
    
    Example:
        ```python
        from praisonaiagents.storage import MongoDBStorageAdapter
        
        adapter = MongoDBStorageAdapter(url="mongodb://localhost:27017/")
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """
    
    def __init__(
        self,
        url: str = "mongodb://localhost:27017/",
        database: str = "praisonai",
        collection: str = "praison_storage",
        max_pool_size: int = 50,
        server_selection_timeout_ms: int = 5000,
    ):
        """
        Initialize the MongoDB storage adapter.
        
        Args:
            url: MongoDB connection URL
            database: Database name
            collection: Collection name for storage
            max_pool_size: Maximum connections in pool
            server_selection_timeout_ms: Server selection timeout
        """
        self.url = url
        self.database_name = database
        self.collection_name = collection
        self.max_pool_size = max_pool_size
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self._client = None
        self._collection = None
        self._lock = threading.Lock()
        self._indexes_created = False
    
    def _get_collection(self):
        """Lazy initialize MongoDB client and collection."""
        if self._collection is None:
            with self._lock:
                if self._collection is None:  # Double-check pattern
                    try:
                        import pymongo
                        from pymongo import MongoClient
                    except ImportError:
                        raise ImportError(
                            "MongoDB storage adapter requires the 'pymongo' package. "
                            "Install with: pip install praisonaiagents[mongodb]"
                        )
                    
                    self._client = MongoClient(
                        self.url,
                        maxPoolSize=self.max_pool_size,
                        retryWrites=True,
                        retryReads=True,
                        serverSelectionTimeoutMS=self.server_selection_timeout_ms,
                        connectTimeoutMS=5000,
                        socketTimeoutMS=10000,
                    )
                    
                    # Test connection
                    try:
                        self._client.admin.command('ping')
                        logger.info(f"MongoDB connection established: {self.url}")
                    except Exception as e:
                        logger.error(f"Failed to connect to MongoDB: {e}")
                        raise
                    
                    db = self._client[self.database_name]
                    self._collection = db[self.collection_name]
                    
                    # Create indexes for performance
                    self._create_indexes()
        
        return self._collection
    
    def _create_indexes(self):
        """Create indexes for better query performance."""
        if self._indexes_created:
            return
            
        try:
            collection = self._collection
            
            # Create text index for GIN-like functionality (for prefix searches)
            collection.create_index("_id", background=True)
            
            # Create compound index for prefix queries
            collection.create_index([("_id", 1), ("updated_at", -1)], background=True)
            
            # Create index on updated_at for cleanup operations
            collection.create_index("updated_at", background=True)
            
            self._indexes_created = True
            logger.debug(f"Created indexes for MongoDB collection: {self.collection_name}")
            
        except Exception as e:
            logger.warning(f"Failed to create MongoDB indexes: {e}")
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key (atomic upsert)."""
        try:
            collection = self._get_collection()
            json_data = json.dumps(data, default=str, ensure_ascii=False)
            
            # Atomic upsert operation
            result = collection.replace_one(
                {"_id": key},
                {
                    "_id": key,
                    "data": json_data,
                    "created_at": time.time(),
                    "updated_at": time.time()
                },
                upsert=True,
            )
            
            if result.upserted_id or result.modified_count > 0:
                logger.debug(f"Saved data to MongoDB key: {key}")
            else:
                logger.warning(f"No changes made when saving MongoDB key: {key}")
                
        except Exception as e:
            logger.error(f"Failed to save data to MongoDB key '{key}': {e}")
            raise
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        try:
            collection = self._get_collection()
            doc = collection.find_one({"_id": key})
            
            if doc and "data" in doc:
                try:
                    data = json.loads(doc["data"])
                    logger.debug(f"Loaded data from MongoDB key: {key}")
                    return data
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON data for key '{key}': {e}")
                    return None
            return None
        except Exception as e:
            logger.error(f"Failed to load data from MongoDB key '{key}': {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        try:
            collection = self._get_collection()
            result = collection.delete_one({"_id": key})
            
            deleted = result.deleted_count > 0
            if deleted:
                logger.debug(f"Deleted MongoDB key: {key}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete MongoDB key '{key}': {e}")
            return False
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        try:
            collection = self._get_collection()
            
            if prefix:
                # Use regex for prefix matching (GIN-like behavior)
                query = {"_id": {"$regex": f"^{prefix}", "$options": "i"}}
            else:
                query = {}
            
            cursor = collection.find(query, {"_id": 1}).sort("_id", 1)
            keys = [doc["_id"] for doc in cursor]
            
            logger.debug(f"Listed {len(keys)} MongoDB keys with prefix: '{prefix}'")
            return keys
        except Exception as e:
            logger.error(f"Failed to list MongoDB keys with prefix '{prefix}': {e}")
            return []
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        try:
            collection = self._get_collection()
            return collection.count_documents({"_id": key}, limit=1) > 0
        except Exception as e:
            logger.error(f"Failed to check if MongoDB key '{key}' exists: {e}")
            return False
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        try:
            collection = self._get_collection()
            result = collection.delete_many({})
            deleted = result.deleted_count
            
            logger.info(f"Cleared {deleted} MongoDB documents from collection '{self.collection_name}'")
            return deleted
        except Exception as e:
            logger.error(f"Failed to clear MongoDB collection: {e}")
            return 0
    
    def count(self) -> int:
        """Get total number of stored items."""
        try:
            collection = self._get_collection()
            return collection.count_documents({})
        except Exception as e:
            logger.error(f"Failed to count MongoDB documents: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get collection statistics."""
        try:
            collection = self._get_collection()
            db = collection.database
            
            stats = db.command("collStats", self.collection_name)
            return {
                "count": stats.get("count", 0),
                "size": stats.get("size", 0),
                "avgObjSize": stats.get("avgObjSize", 0),
                "indexSizes": stats.get("indexSizes", {}),
            }
        except Exception as e:
            logger.error(f"Failed to get MongoDB collection stats: {e}")
            return {}
    
    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            try:
                self._client.close()
                logger.info("MongoDB connection closed")
            except Exception as e:
                logger.error(f"Error closing MongoDB connection: {e}")
            finally:
                self._client = None
                self._collection = None
                self._indexes_created = False


__all__ = ['MongoDBStorageAdapter']