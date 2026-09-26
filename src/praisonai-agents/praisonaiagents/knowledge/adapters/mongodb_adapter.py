"""
MongoDB Knowledge Adapter for PraisonAI.

Implements KnowledgeStoreProtocol using MongoDB as the backend.
Extracted from knowledge.py to follow protocol-driven architecture.

LAZY IMPORT: pymongo is only imported when this adapter is instantiated.
"""

import os
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
    
    def __init__(self, config: Dict[str, Any], verbose: int = 0, **kwargs):
        """
        Initialize MongoDB knowledge adapter.
        
        Args:
            config: Configuration dictionary containing vector_store config
            verbose: Verbosity level (accepted for interface compatibility)
            **kwargs: Additional keyword arguments (ignored)
        """
        self._verbose = verbose
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
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Add content to knowledge store.
        
        Args:
            text: Content to add
            metadata: Optional metadata dictionary
            user_id: Optional user scope for tenant isolation
            agent_id: Optional agent scope for tenant isolation
            run_id: Optional run scope for tenant isolation
            **kwargs: Additional parameters
            
        Returns:
            Document ID of inserted content

        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        from ..protocols import require_scope
        require_scope(user_id, agent_id, run_id, "add", backend="mongodb")
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
                "user_id": user_id,
                "agent_id": agent_id,
                "run_id": run_id,
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
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search knowledge store.
        
        Args:
            query: Search query
            limit: Maximum number of results
            user_id: Optional user scope for tenant isolation
            agent_id: Optional agent scope for tenant isolation
            run_id: Optional run scope for tenant isolation
            filters: Optional metadata filters applied to the query
            **kwargs: Additional search parameters
            
        Returns:
            List of matching documents

        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        from ..protocols import require_scope
        require_scope(user_id, agent_id, run_id, "search", backend="mongodb")
        try:
            results = []

            # Build tenant/scope filter honored by both vector and text search
            scope_filter = {
                k: v for k, v in {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                }.items() if v is not None
            }

            # Fold metadata filters in alongside the scope so a filtered search
            # returns the same subset chroma/mem0 already return instead of
            # silently discarding the filters (issue #5319).
            if filters:
                for key, value in filters.items():
                    scope_filter[f"metadata.{key}"] = value
            
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
                    vector_search_stage = {
                        "$vectorSearch": {
                            "index": "default",  # Assumes default vector index name
                            "path": "embedding",
                            "queryVector": query_embedding,
                            "numCandidates": limit * 10,
                            "limit": limit
                        }
                    }
                    if scope_filter:
                        vector_search_stage["$vectorSearch"]["filter"] = scope_filter
                    pipeline = [
                        vector_search_stage,
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
            text_query: Dict[str, Any] = {"$text": {"$search": query}}
            text_query.update(scope_filter)
            text_results = self.collection.find(
                text_query,
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
    
    def get(self, item_id: str, **kwargs):
        """Get a specific document by ID from the knowledge store.

        Returns a ``SearchResultItem`` (or ``None``) so the result shape matches
        the shared KnowledgeStoreProtocol and the other adapters — a caller that
        reads ``.text``/``.metadata`` or calls ``.to_dict()`` must not break when
        it switches to the MongoDB backend (issue #5319).
        """
        from ..models import SearchResultItem
        try:
            from bson import ObjectId
            doc = self.collection.find_one({"_id": ObjectId(item_id)})
            if not doc:
                return None
            return SearchResultItem(
                id=str(doc["_id"]),
                text=doc.get("content", ""),
                metadata=doc.get("metadata", {}) or {},
                score=1.0,
            )
        except Exception as e:
            logger.error(f"Failed to get document {item_id}: {e}")
            return None

    def get_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
        **kwargs
    ):
        """Get all documents matching the given scope.

        Returns a ``SearchResult`` to match the shared KnowledgeStoreProtocol
        and the other adapters.

        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        from ..models import SearchResult, SearchResultItem
        from ..protocols import require_scope
        require_scope(user_id, agent_id, run_id, "get_all", backend="mongodb")
        try:
            scope_filter = {
                k: v for k, v in {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                }.items() if v is not None
            }
            items = []
            for doc in self.collection.find(scope_filter).limit(limit):
                items.append(SearchResultItem(
                    id=str(doc["_id"]),
                    text=doc.get("content", ""),
                    metadata=doc.get("metadata", {}) or {},
                    score=1.0,
                ))
            return SearchResult(results=items)
        except Exception as e:
            logger.error(f"Failed to get_all from MongoDB: {e}")
            return SearchResult(results=[])

    def update(self, item_id: str, content: Any, **kwargs):
        """Update an existing document's content/metadata by ID.

        Returns an ``AddResult`` to match the shared KnowledgeStoreProtocol and
        the other adapters (issue #5319).
        """
        from ..models import AddResult
        try:
            from bson import ObjectId
            update_fields: Dict[str, Any] = {"content": str(content)}
            if "metadata" in kwargs and kwargs["metadata"] is not None:
                update_fields["metadata"] = kwargs["metadata"]
            result = self.collection.update_one(
                {"_id": ObjectId(item_id)},
                {"$set": update_fields}
            )
            if result.matched_count > 0:
                return AddResult(success=True, id=item_id)
            return AddResult(success=False, message=f"No document matched id {item_id}")
        except Exception as e:
            logger.error(f"Failed to update document {item_id}: {e}")
            return AddResult(success=False, message=str(e))

    def delete_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Delete all documents matching the given scope.

        Enforces the same tenant-scope contract as the mem0 backend: an
        unscoped call raises ``ScopeRequiredError`` instead of silently wiping
        every tenant's documents from the (typically shared) collection.

        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        from ..protocols import require_scope
        require_scope(user_id, agent_id, run_id, "delete_all", backend="mongodb")
        try:
            scope_filter = {
                k: v for k, v in {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "run_id": run_id,
                }.items() if v is not None
            }
            self.collection.delete_many(scope_filter)
            return True
        except Exception as e:
            logger.error(f"Failed to delete_all from MongoDB: {e}")
            return False

    def close(self):
        """Close MongoDB connection."""
        if hasattr(self, 'client'):
            self.client.close()