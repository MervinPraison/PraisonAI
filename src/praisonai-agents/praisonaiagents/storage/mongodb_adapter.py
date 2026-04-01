"""
MongoDB Storage Adapter for PraisonAI Agents.

Provides MongoDB-based storage backend implementing StorageBackendProtocol.
Uses lazy imports for the pymongo dependency to avoid module-level import overhead.

Example:
    ```python
    from praisonaiagents.storage import MongoDBStorageAdapter
    
    # Basic usage with defaults
    adapter = MongoDBStorageAdapter()
    adapter.save("session_123", {"messages": []})
    data = adapter.load("session_123")
    
    # Custom MongoDB configuration
    adapter = MongoDBStorageAdapter(
        uri="mongodb://localhost:27017",
        database="myapp",
        collection="praisonai_storage"
    )
    ```
"""

import threading
from typing import Any, Dict, List, Optional
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class MongoDBStorageAdapter:
    """
    MongoDB-based storage backend implementing StorageBackendProtocol.
    
    Stores data as documents in a MongoDB collection.
    Thread-safe and supports connection pooling.
    """
    
    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        database: str = "praisonai",
        collection: str = "storage",
        server_selection_timeout_ms: int = 5000,
        **kwargs
    ):
        """
        Initialize MongoDB storage adapter.
        
        Args:
            uri: MongoDB connection URI
            database: Database name
            collection: Collection name for storing data
            server_selection_timeout_ms: Server selection timeout in milliseconds
            **kwargs: Additional PyMongo client parameters
        """
        self.uri = uri
        self.database_name = database
        self.collection_name = collection
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self.client_kwargs = kwargs
        self._client = None
        self._database = None
        self._collection = None
        self._lock = threading.Lock()
    
    def _get_collection(self):
        """Get MongoDB collection with lazy initialization."""
        if self._collection is None:
            with self._lock:
                if self._collection is None:
                    try:
                        import pymongo
                    except ImportError:
                        raise ImportError(
                            "PyMongo not installed. Install with: pip install praisonaiagents[mongodb]"
                        )
                    
                    # Create client with connection pooling
                    self._client = pymongo.MongoClient(
                        self.uri,
                        serverSelectionTimeoutMS=self.server_selection_timeout_ms,
                        **self.client_kwargs
                    )
                    
                    # Test connection
                    try:
                        self._client.admin.command('ping')
                    except Exception as e:
                        self._client.close()
                        self._client = None
                        raise ConnectionError(f"Failed to connect to MongoDB: {e}")
                    
                    self._database = self._client[self.database_name]
                    self._collection = self._database[self.collection_name]
                    
                    # Create index on key for performance
                    try:
                        self._collection.create_index("key", unique=True, background=True)
                    except Exception as e:
                        logger.warning(f"Could not create MongoDB index: {e}")
        
        return self._collection
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """
        Save data to MongoDB.
        
        Args:
            key: Unique identifier for the data
            data: Dictionary to save
            
        Raises:
            ConnectionError: If MongoDB is unavailable
            ValueError: If data cannot be stored
        """
        collection = self._get_collection()
        
        try:
            document = {
                "key": key,
                "data": data
            }
            
            # Use upsert to replace if exists or insert if new
            collection.replace_one(
                {"key": key},
                document,
                upsert=True
            )
            logger.debug(f"Saved data to MongoDB key: {key}")
        except Exception as e:
            logger.error(f"Failed to save data to MongoDB key {key}: {e}")
            raise
    
    def load(self, key: str) -> Any:
        """
        Load data from MongoDB.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            The stored data, or None if not found
            
        Raises:
            ConnectionError: If MongoDB is unavailable
        """
        collection = self._get_collection()
        
        try:
            document = collection.find_one({"key": key})
            if document is None:
                logger.debug(f"No data found for MongoDB key: {key}")
                return None
            
            data = document.get("data")
            logger.debug(f"Loaded data from MongoDB key: {key}")
            return data
        except Exception as e:
            logger.error(f"Failed to load data from MongoDB key {key}: {e}")
            raise
    
    def delete(self, key: str) -> bool:
        """
        Delete data from MongoDB.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ConnectionError: If MongoDB is unavailable
        """
        collection = self._get_collection()
        
        try:
            result = collection.delete_one({"key": key})
            success = result.deleted_count > 0
            if success:
                logger.debug(f"Deleted MongoDB key: {key}")
            else:
                logger.debug(f"MongoDB key not found for deletion: {key}")
            return success
        except Exception as e:
            logger.error(f"Failed to delete MongoDB key {key}: {e}")
            raise
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """
        List all keys, optionally filtered by prefix.
        
        Args:
            prefix: Optional prefix to filter keys
            
        Returns:
            List of matching keys
            
        Raises:
            ConnectionError: If MongoDB is unavailable
        """
        collection = self._get_collection()
        
        try:
            # Build query filter
            query = {}
            if prefix:
                # Use regex for prefix matching
                query["key"] = {"$regex": f"^{prefix}"}
            
            # Get only the key field
            cursor = collection.find(query, {"key": 1, "_id": 0})
            keys = [doc["key"] for doc in cursor]
            
            logger.debug(f"Found {len(keys)} keys matching prefix: {prefix}")
            return sorted(keys)
        except Exception as e:
            logger.error(f"Failed to list MongoDB keys with prefix {prefix}: {e}")
            raise
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists in MongoDB.
        
        Args:
            key: Unique identifier to check
            
        Returns:
            True if exists, False otherwise
            
        Raises:
            ConnectionError: If MongoDB is unavailable
        """
        collection = self._get_collection()
        
        try:
            count = collection.count_documents({"key": key}, limit=1)
            exists = count > 0
            logger.debug(f"MongoDB key {'exists' if exists else 'does not exist'}: {key}")
            return exists
        except Exception as e:
            logger.error(f"Failed to check existence of MongoDB key {key}: {e}")
            raise
    
    def close(self) -> None:
        """Close MongoDB connection if open."""
        if self._client is not None:
            try:
                self._client.close()
                logger.debug("Closed MongoDB connection")
            except Exception as e:
                logger.warning(f"Error closing MongoDB connection: {e}")
            finally:
                self._client = None
                self._database = None
                self._collection = None


__all__ = ["MongoDBStorageAdapter"]