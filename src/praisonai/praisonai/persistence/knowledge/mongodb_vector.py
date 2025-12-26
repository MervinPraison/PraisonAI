"""
MongoDB Vector Search implementation of KnowledgeStore.

Requires: pymongo
Install: pip install pymongo
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class MongoDBVectorKnowledgeStore(KnowledgeStore):
    """
    MongoDB Atlas Vector Search store for knowledge/RAG.
    
    Uses MongoDB Atlas Vector Search capabilities.
    
    Example:
        store = MongoDBVectorKnowledgeStore(
            url="mongodb+srv://...",
            database="praisonai",
            collection="vectors"
        )
    """
    
    def __init__(
        self,
        url: str = "mongodb://localhost:27017",
        database: str = "praisonai",
        collection: str = "vectors",
        index_name: str = "vector_index",
        embedding_field: str = "embedding",
        text_field: str = "content",
        embedding_dim: int = 1536,
    ):
        """
        Initialize MongoDB Vector store.
        
        Args:
            url: MongoDB connection URL
            database: Database name
            collection: Collection name
            index_name: Vector search index name
            embedding_field: Field name for embeddings
            text_field: Field name for text content
            embedding_dim: Embedding dimension
        """
        self.url = url
        self.database_name = database
        self.collection_name = collection
        self.index_name = index_name
        self.embedding_field = embedding_field
        self.text_field = text_field
        self.embedding_dim = embedding_dim
        
        self._client = None
        self._db = None
        self._collection = None
        self._initialized = False
    
    def _init_client(self):
        """Initialize MongoDB client lazily."""
        if self._initialized:
            return
        
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ImportError(
                "pymongo is required for MongoDB Vector support. "
                "Install with: pip install pymongo"
            )
        
        self._client = MongoClient(self.url)
        self._db = self._client[self.database_name]
        self._collection = self._db[self.collection_name]
        self._initialized = True
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create collection (MongoDB creates on first insert)."""
        self._init_client()
        # MongoDB creates collections automatically on first insert
        # Vector search index must be created via Atlas UI or API
        logger.info(
            f"Collection '{name}' will be created on first insert. "
            f"Note: Vector search index must be created via MongoDB Atlas."
        )
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        self._init_client()
        try:
            self._db.drop_collection(name)
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if collection exists."""
        self._init_client()
        return name in self._db.list_collection_names()
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        self._init_client()
        return self._db.list_collection_names()
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents into collection."""
        self._init_client()
        
        coll = self._db[collection]
        ids = []
        
        for doc in documents:
            mongo_doc = {
                "_id": doc.id,
                self.text_field: doc.content,
                "metadata": doc.metadata or {},
                "content_hash": doc.content_hash,
                "created_at": doc.created_at,
            }
            
            if doc.embedding:
                mongo_doc[self.embedding_field] = doc.embedding
            
            try:
                coll.insert_one(mongo_doc)
                ids.append(doc.id)
            except Exception as e:
                logger.warning(f"Failed to insert document {doc.id}: {e}")
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents into collection."""
        self._init_client()
        
        coll = self._db[collection]
        ids = []
        
        for doc in documents:
            mongo_doc = {
                self.text_field: doc.content,
                "metadata": doc.metadata or {},
                "content_hash": doc.content_hash,
                "created_at": doc.created_at,
            }
            
            if doc.embedding:
                mongo_doc[self.embedding_field] = doc.embedding
            
            try:
                coll.replace_one(
                    {"_id": doc.id},
                    {"_id": doc.id, **mongo_doc},
                    upsert=True
                )
                ids.append(doc.id)
            except Exception as e:
                logger.warning(f"Failed to upsert document {doc.id}: {e}")
        
        return ids
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents using vector search."""
        self._init_client()
        
        coll = self._db[collection]
        
        # Build aggregation pipeline for vector search
        pipeline = [
            {
                "$vectorSearch": {
                    "index": self.index_name,
                    "path": self.embedding_field,
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,
                    "limit": limit
                }
            },
            {
                "$project": {
                    "_id": 1,
                    self.text_field: 1,
                    "metadata": 1,
                    "content_hash": 1,
                    "created_at": 1,
                    "score": {"$meta": "vectorSearchScore"}
                }
            }
        ]
        
        # Add filter if provided
        if filters:
            pipeline[0]["$vectorSearch"]["filter"] = filters
        
        try:
            results = list(coll.aggregate(pipeline))
            
            documents = []
            for doc in results:
                score = doc.get("score", 0)
                if score_threshold and score < score_threshold:
                    continue
                
                documents.append(KnowledgeDocument(
                    id=str(doc["_id"]),
                    content=doc.get(self.text_field, ""),
                    metadata={**(doc.get("metadata") or {}), "score": score},
                    content_hash=doc.get("content_hash"),
                    created_at=doc.get("created_at", 0)
                ))
            
            return documents
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        self._init_client()
        
        coll = self._db[collection]
        documents = []
        
        for doc_id in ids:
            try:
                doc = coll.find_one({"_id": doc_id})
                if doc:
                    documents.append(KnowledgeDocument(
                        id=str(doc["_id"]),
                        content=doc.get(self.text_field, ""),
                        embedding=doc.get(self.embedding_field),
                        metadata=doc.get("metadata"),
                        content_hash=doc.get("content_hash"),
                        created_at=doc.get("created_at", 0)
                    ))
            except Exception as e:
                logger.warning(f"Failed to get document {doc_id}: {e}")
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents by IDs or filters."""
        self._init_client()
        
        coll = self._db[collection]
        
        if ids:
            result = coll.delete_many({"_id": {"$in": ids}})
            return result.deleted_count
        elif filters:
            result = coll.delete_many(filters)
            return result.deleted_count
        else:
            return 0
    
    def count(self, collection: str) -> int:
        """Count documents in collection."""
        self._init_client()
        return self._db[collection].count_documents({})
    
    def close(self) -> None:
        """Close the connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            self._collection = None
            self._initialized = False
