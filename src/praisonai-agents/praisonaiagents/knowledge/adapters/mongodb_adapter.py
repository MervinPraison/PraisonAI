"""
MongoDB Knowledge Adapter for PraisonAI.

Implements KnowledgeStoreProtocol using MongoDB as the backend.
Extracted from knowledge.py to follow protocol-driven architecture.

LAZY IMPORT: pymongo is only imported when this adapter is instantiated.
"""

import os
import logging
from praisonaiagents._logging import get_logger
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = get_logger(__name__)

class MongoDBKnowledgeAdapter:
    """
    MongoDB-based knowledge store adapter.
    
    Extracted from the main Knowledge class to follow adapter pattern.
    Uses lazy imports to avoid heavy dependencies in core SDK.
    
    Features:
    - Vector search support (MongoDB Atlas)
    - Automatic indexing
    - Connection pooling
    - Embedding model integration
    
    Usage:
        adapter = MongoDBKnowledgeAdapter(config={
            "vector_store": {
                "config": {
                    "connection_string": "mongodb://localhost:27017/",
                    "database": "praisonai",
                    "collection": "knowledge_base"
                }
            }
        })
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MongoDB knowledge adapter.
        
        Args:
            config: Configuration dictionary containing vector_store config
        """
        self.config = config
        self.vector_store_config = config.get("vector_store", {}).get("config", {})
        self.connection_string = self.vector_store_config.get("connection_string", "mongodb://localhost:27017/")
        self.database_name = self.vector_store_config.get("database", "praisonai")
        self.collection_name = self.vector_store_config.get("collection", "knowledge_base")
        self.use_vector_search = self.vector_store_config.get("use_vector_search", True)
        
        # Initialize embedding model before MongoDB to ensure embedding_model_name is available
        self._init_embedding_model()
        
        # Initialize MongoDB client (lazy import)
        self._init_mongodb()
    
    def _init_mongodb(self):
        """Initialize MongoDB client and collection with lazy import."""
        try:
            # Lazy import of pymongo
            from pymongo import MongoClient
            
            self.client = MongoClient(
                self.connection_string,
                maxPoolSize=50,
                retryWrites=True,
                retryReads=True
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            # Setup database and collection
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # Create indexes
            self._create_indexes()
            
        except ImportError:
            raise ImportError(
                "MongoDB support requires pymongo. Install with: pip install pymongo"
            )
        except Exception as e:
            raise Exception(f"Failed to initialize MongoDB: {e}")
    
    def _init_embedding_model(self):
        """Initialize embedding model from config using litellm for unified provider support."""
        try:
            # Set up embedding model based on config
            embedder_config = self.config.get("embedder", {})
            provider = embedder_config.get("provider", "openai")
            model_name = embedder_config.get("config", {}).get("model", "text-embedding-3-small")
            
            # Store model name for later use
            self.embedding_model_name = f"{provider}/{model_name}" if provider != "openai" else model_name
            
            # Lazy import of litellm for embedding
            import litellm
            
            self.embedding_model = litellm
            
        except Exception as e:
            logger.warning(f"Failed to initialize embedding model: {e}")
            self.embedding_model = None
            self.embedding_model_name = "text-embedding-3-small"
    
    def _create_indexes(self):
        """Create necessary indexes for efficient querying."""
        try:
            # Create text index for content search
            self.collection.create_index([("content", "text")])
            
            # Create index on metadata fields
            self.collection.create_index([("metadata.source", 1)])
            self.collection.create_index([("timestamp", -1)])
            
            # Create vector search index if enabled and using Atlas
            if self.use_vector_search and self._is_atlas_connection():
                self._create_vector_index()
                
        except Exception as e:
            logger.warning(f"Failed to create indexes: {e}")
    
    def _is_atlas_connection(self) -> bool:
        """Check if connection is to MongoDB Atlas."""
        return "mongodb.net" in self.connection_string or "mongodb+srv://" in self.connection_string
    
    def _create_vector_index(self):
        """Create vector search index for Atlas."""
        try:
            # This would typically be done through Atlas UI or API
            # For now, just log the requirement
            logger.info(
                f"Vector search enabled. Please ensure vector index exists on collection "
                f"{self.collection_name} with path 'embedding' and similarity 'cosine'"
            )
        except Exception as e:
            logger.warning(f"Failed to create vector index: {e}")
    
    def add(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Add content to knowledge store.
        
        Args:
            text: Content to add
            metadata: Optional metadata dictionary
            **kwargs: Additional parameters
            
        Returns:
            Document ID of inserted content
        """
        try:
            # Generate embedding if model is available
            embedding = None
            if self.embedding_model and text:
                try:
                    response = self.embedding_model.embedding(
                        model=self.embedding_model_name,
                        input=[text]
                    )
                    embedding = response.data[0].embedding
                except Exception as e:
                    logger.warning(f"Failed to generate embedding: {e}")
            
            # Prepare document
            document = {
                "content": text,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow(),
                "embedding": embedding
            }
            
            # Insert document
            result = self.collection.insert_one(document)
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Failed to add content to MongoDB: {e}")
            raise
    
    def search(
        self,
        query: str,
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge store.
        
        Args:
            query: Search query
            limit: Maximum number of results
            **kwargs: Additional search parameters
            
        Returns:
            List of matching documents
        """
        try:
            results = []
            
            # Try vector search first if available
            if self.use_vector_search and self.embedding_model and self._is_atlas_connection():
                try:
                    # Generate query embedding
                    response = self.embedding_model.embedding(
                        model=self.embedding_model_name,
                        input=[query]
                    )
                    query_embedding = response.data[0].embedding
                    
                    # Vector search pipeline
                    pipeline = [
                        {
                            "$vectorSearch": {
                                "index": "default",  # Assumes default vector index name
                                "path": "embedding",
                                "queryVector": query_embedding,
                                "numCandidates": limit * 10,
                                "limit": limit
                            }
                        },
                        {
                            "$project": {
                                "_id": 1,
                                "content": 1,
                                "metadata": 1,
                                "timestamp": 1,
                                "score": {"$meta": "vectorSearchScore"}
                            }
                        }
                    ]
                    
                    vector_results = list(self.collection.aggregate(pipeline))
                    
                    # Format results
                    for doc in vector_results:
                        results.append({
                            "id": str(doc["_id"]),
                            "text": doc["content"],
                            "metadata": doc.get("metadata", {}),
                            "score": doc.get("score", 0.0),
                            "timestamp": doc.get("timestamp")
                        })
                    
                    if results:
                        return results
                        
                except Exception as e:
                    logger.warning(f"Vector search failed, falling back to text search: {e}")
            
            # Fallback to text search
            text_results = self.collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            
            for doc in text_results:
                results.append({
                    "id": str(doc["_id"]),
                    "text": doc["content"],
                    "metadata": doc.get("metadata", {}),
                    "score": doc.get("score", 0.0),
                    "timestamp": doc.get("timestamp")
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search MongoDB: {e}")
            return []
    
    def delete(self, document_id: str) -> bool:
        """
        Delete document from knowledge store.
        
        Args:
            document_id: ID of document to delete
            
        Returns:
            True if document was deleted, False otherwise
        """
        try:
            from bson import ObjectId
            result = self.collection.delete_one({"_id": ObjectId(document_id)})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            return False
    
    def close(self):
        """Close MongoDB connection."""
        if hasattr(self, 'client'):
            self.client.close()