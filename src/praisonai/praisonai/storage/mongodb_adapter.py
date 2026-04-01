"""
MongoDB Storage Adapter for PraisonAI.

Implements StorageBackendProtocol using MongoDB for document storage.
This is the wrapper implementation that contains the heavy MongoDB dependency.
"""

import json
import re
import time
from typing import Dict, Any, List, Optional


class MongoDBStorageAdapter:
    """
    MongoDB-based storage backend adapter.
    
    Uses MongoDB for document-oriented data storage.
    Implements StorageBackendProtocol from praisonaiagents.storage.protocols.
    
    Example:
        ```python
        from praisonai.storage import MongoDBStorageAdapter
        
        adapter = MongoDBStorageAdapter(
            url="mongodb://localhost:27017/",
            database="praisonai"
        )
        adapter.save("session_123", {"messages": []})
        data = adapter.load("session_123")
        ```
    """
    
    def __init__(
        self,
        url: str = "mongodb://localhost:27017/",
        database: str = "praisonai",
        collection: str = "storage",
        max_pool_size: int = 50,
        min_pool_size: int = 5,
        max_idle_time_ms: int = 30000,
        server_selection_timeout_ms: int = 5000,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize the MongoDB storage adapter.
        
        Args:
            url: MongoDB connection URL
            database: Database name
            collection: Collection name for storing data
            max_pool_size: Maximum connection pool size
            min_pool_size: Minimum connection pool size  
            max_idle_time_ms: Maximum idle time for connections
            server_selection_timeout_ms: Server selection timeout
            username: Optional username for authentication
            password: Optional password for authentication
        """
        self.url = url
        self.database = database
        self.collection_name = collection
        self.max_pool_size = max_pool_size
        self.min_pool_size = min_pool_size
        self.max_idle_time_ms = max_idle_time_ms
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self.username = username
        self.password = password
        self._client = None
        self._collection = None
    
    def _get_collection(self):
        """Lazy initialize MongoDB client and collection."""
        if self._collection is None:
            try:
                import pymongo
                from pymongo import MongoClient
            except ImportError:
                raise ImportError(
                    "MongoDB storage adapter requires the 'pymongo' package. "
                    "Install with: pip install 'praisonai[mongodb]'"
                )
            
            # Build connection parameters
            client_kwargs = {
                "maxPoolSize": self.max_pool_size,
                "minPoolSize": self.min_pool_size,
                "maxIdleTimeMS": self.max_idle_time_ms,
                "serverSelectionTimeoutMS": self.server_selection_timeout_ms,
                "retryWrites": True,
                "retryReads": True,
            }
            
            if self.username and self.password:
                client_kwargs["username"] = self.username
                client_kwargs["password"] = self.password
            
            self._client = MongoClient(self.url, **client_kwargs)
            db = self._client[self.database]
            self._collection = db[self.collection_name]
            
            # Create index for better performance
            try:
                self._collection.create_index("_id", unique=True)
                self._collection.create_index("updated_at")
            except Exception:
                # Index creation can fail if it already exists, which is fine
                pass
                
        return self._collection
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key (upsert)."""
        collection = self._get_collection()
        
        try:
            # Store as JSON string for consistency
            json_data = json.dumps(data, default=str, ensure_ascii=False)
            now = time.time()
            
            collection.update_one(
                {"_id": key},
                {
                    "$set": {
                        "data": json_data,
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "created_at": now,
                    },
                },
                upsert=True,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to save data to MongoDB: {e}") from e
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load data by key."""
        collection = self._get_collection()
        
        try:
            doc = collection.find_one({"_id": key})
            if doc and "data" in doc:
                try:
                    return json.loads(doc["data"])
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON data for key '{key}': {e}") from e
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to load data from MongoDB: {e}") from e
    
    def delete(self, key: str) -> bool:
        """Delete data by key."""
        collection = self._get_collection()
        
        try:
            result = collection.delete_one({"_id": key})
            return result.deleted_count > 0
        except Exception as e:
            raise RuntimeError(f"Failed to delete data from MongoDB: {e}") from e
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        collection = self._get_collection()
        
        try:
            if prefix:
                # Escape regex metacharacters to prevent ReDoS / unexpected matches
                escaped = re.escape(prefix)
                cursor = collection.find(
                    {"_id": {"$regex": f"^{escaped}"}},
                    {"_id": 1}
                ).sort("_id", 1)
            else:
                cursor = collection.find({}, {"_id": 1}).sort("_id", 1)
                
            return [doc["_id"] for doc in cursor]
        except Exception as e:
            raise RuntimeError(f"Failed to list keys from MongoDB: {e}") from e
    
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        collection = self._get_collection()
        
        try:
            return collection.count_documents({"_id": key}, limit=1) > 0
        except Exception as e:
            raise RuntimeError(f"Failed to check key existence in MongoDB: {e}") from e
    
    def clear(self) -> int:
        """Clear all data. Returns number of items deleted."""
        collection = self._get_collection()
        
        try:
            result = collection.delete_many({})
            return result.deleted_count
        except Exception as e:
            raise RuntimeError(f"Failed to clear data from MongoDB: {e}") from e
    
    def ping(self) -> bool:
        """Test connection to MongoDB."""
        try:
            collection = self._get_collection()
            # Try to run a simple command
            collection.database.client.admin.command('ping')
            return True
        except Exception:
            return False
    
    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            try:
                self._client.close()
            finally:
                self._client = None
                self._collection = None