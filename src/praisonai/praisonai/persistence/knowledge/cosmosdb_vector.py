"""
Azure Cosmos DB Vector implementation of KnowledgeStore.

Supports both MongoDB API and vCore modes.

Requires: pymongo (for MongoDB API) or azure-cosmos (for SQL API)
Install: pip install pymongo  # or pip install azure-cosmos
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class CosmosDBVectorKnowledgeStore(KnowledgeStore):
    """
    Azure Cosmos DB vector store for knowledge/RAG.
    
    Supports MongoDB API with vector search capabilities.
    
    Example:
        store = CosmosDBVectorKnowledgeStore(
            connection_string="mongodb+srv://...",
            database="praisonai",
            collection="vectors"
        )
    """
    
    def __init__(
        self,
        connection_string: Optional[str] = None,
        database: str = "praisonai",
        collection: str = "vectors",
        index_name: str = "vector_index",
        embedding_field: str = "embedding",
        text_field: str = "content",
        embedding_dim: int = 1536,
        api_mode: str = "mongodb",  # "mongodb" or "sql"
    ):
        """
        Initialize Cosmos DB Vector store.
        
        Args:
            connection_string: Azure Cosmos DB connection string
            database: Database name
            collection: Collection name
            index_name: Vector search index name
            embedding_field: Field name for embeddings
            text_field: Field name for text content
            embedding_dim: Embedding dimension
            api_mode: API mode ("mongodb" or "sql")
        """
        self.connection_string = connection_string
        self.database_name = database
        self.collection_name = collection
        self.index_name = index_name
        self.embedding_field = embedding_field
        self.text_field = text_field
        self.embedding_dim = embedding_dim
        self.api_mode = api_mode
        
        self._client = None
        self._db = None
        self._collection = None
        self._initialized = False
    
    def _init_client(self):
        """Initialize Cosmos DB client lazily."""
        if self._initialized:
            return
        
        if not self.connection_string:
            import os
            self.connection_string = os.getenv("COSMOS_CONNECTION_STRING")
            if not self.connection_string:
                raise ValueError(
                    "connection_string required. Set COSMOS_CONNECTION_STRING env var."
                )
        
        if self.api_mode == "mongodb":
            self._init_mongodb_client()
        else:
            self._init_sql_client()
        
        self._initialized = True
    
    def _init_mongodb_client(self):
        """Initialize MongoDB API client."""
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ImportError(
                "pymongo is required for Cosmos DB MongoDB API. "
                "Install with: pip install pymongo"
            )
        
        self._client = MongoClient(self.connection_string)
        self._db = self._client[self.database_name]
        self._collection = self._db[self.collection_name]
    
    def _init_sql_client(self):
        """Initialize SQL API client."""
        try:
            from azure.cosmos import CosmosClient
        except ImportError:
            raise ImportError(
                "azure-cosmos is required for Cosmos DB SQL API. "
                "Install with: pip install azure-cosmos"
            )
        
        self._client = CosmosClient.from_connection_string(self.connection_string)
        self._db = self._client.get_database_client(self.database_name)
        self._collection = self._db.get_container_client(self.collection_name)
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create collection with vector index."""
        self._init_client()
        
        if self.api_mode == "mongodb":
            # Create vector search index via MongoDB command
            try:
                self._db.command({
                    "createIndexes": name,
                    "indexes": [{
                        "name": self.index_name,
                        "key": {self.embedding_field: "cosmosSearch"},
                        "cosmosSearchOptions": {
                            "kind": "vector-ivf",
                            "numLists": 100,
                            "similarity": distance,
                            "dimensions": dimension
                        }
                    }]
                })
            except Exception as e:
                logger.warning(f"Index creation may require manual setup: {e}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete collection."""
        self._init_client()
        try:
            if self.api_mode == "mongodb":
                self._db.drop_collection(name)
            else:
                self._db.delete_container(name)
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if collection exists."""
        self._init_client()
        if self.api_mode == "mongodb":
            return name in self._db.list_collection_names()
        return True  # SQL API containers are pre-created
    
    def list_collections(self) -> List[str]:
        """List collections."""
        self._init_client()
        if self.api_mode == "mongodb":
            return self._db.list_collection_names()
        return [c["id"] for c in self._db.list_containers()]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        self._init_client()
        
        coll = self._db[collection] if self.api_mode == "mongodb" else self._db.get_container_client(collection)
        ids = []
        
        for doc in documents:
            item = {
                "_id" if self.api_mode == "mongodb" else "id": doc.id,
                self.text_field: doc.content,
                self.embedding_field: doc.embedding,
                "metadata": doc.metadata or {},
                "content_hash": doc.content_hash,
                "created_at": doc.created_at,
            }
            
            try:
                if self.api_mode == "mongodb":
                    coll.insert_one(item)
                else:
                    coll.create_item(item)
                ids.append(doc.id)
            except Exception as e:
                logger.warning(f"Failed to insert {doc.id}: {e}")
        
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents."""
        self._init_client()
        
        coll = self._db[collection] if self.api_mode == "mongodb" else self._db.get_container_client(collection)
        ids = []
        
        for doc in documents:
            item = {
                "_id" if self.api_mode == "mongodb" else "id": doc.id,
                self.text_field: doc.content,
                self.embedding_field: doc.embedding,
                "metadata": doc.metadata or {},
                "content_hash": doc.content_hash,
                "created_at": doc.created_at,
            }
            
            try:
                if self.api_mode == "mongodb":
                    coll.replace_one({"_id": doc.id}, item, upsert=True)
                else:
                    coll.upsert_item(item)
                ids.append(doc.id)
            except Exception as e:
                logger.warning(f"Failed to upsert {doc.id}: {e}")
        
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
        
        if self.api_mode == "mongodb":
            return self._search_mongodb(collection, query_embedding, limit, filters, score_threshold)
        else:
            return self._search_sql(collection, query_embedding, limit, filters, score_threshold)
    
    def _search_mongodb(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int,
        filters: Optional[Dict[str, Any]],
        score_threshold: Optional[float]
    ) -> List[KnowledgeDocument]:
        """MongoDB API vector search."""
        coll = self._db[collection]
        
        pipeline = [
            {
                "$search": {
                    "cosmosSearch": {
                        "vector": query_embedding,
                        "path": self.embedding_field,
                        "k": limit
                    },
                    "returnStoredSource": True
                }
            },
            {
                "$project": {
                    "similarityScore": {"$meta": "searchScore"},
                    self.text_field: 1,
                    "metadata": 1,
                    "content_hash": 1,
                    "created_at": 1
                }
            }
        ]
        
        if filters:
            pipeline.insert(1, {"$match": filters})
        
        try:
            results = list(coll.aggregate(pipeline))
            
            documents = []
            for doc in results:
                score = doc.get("similarityScore", 0)
                if score_threshold and score < score_threshold:
                    continue
                
                documents.append(KnowledgeDocument(
                    id=str(doc.get("_id", "")),
                    content=doc.get(self.text_field, ""),
                    metadata={**(doc.get("metadata") or {}), "score": score},
                    content_hash=doc.get("content_hash"),
                    created_at=doc.get("created_at", 0)
                ))
            
            return documents
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _search_sql(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int,
        filters: Optional[Dict[str, Any]],
        score_threshold: Optional[float]
    ) -> List[KnowledgeDocument]:
        """SQL API vector search (requires DiskANN index)."""
        coll = self._db.get_container_client(collection)
        
        # SQL API uses VectorDistance function
        query = f"""
            SELECT TOP {limit} c.id, c.{self.text_field}, c.metadata, c.content_hash, c.created_at,
                   VectorDistance(c.{self.embedding_field}, @embedding) AS score
            FROM c
            ORDER BY VectorDistance(c.{self.embedding_field}, @embedding)
        """
        
        try:
            results = list(coll.query_items(
                query=query,
                parameters=[{"name": "@embedding", "value": query_embedding}],
                enable_cross_partition_query=True
            ))
            
            documents = []
            for doc in results:
                score = doc.get("score", 0)
                if score_threshold and score < score_threshold:
                    continue
                
                documents.append(KnowledgeDocument(
                    id=doc.get("id", ""),
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
        
        coll = self._db[collection] if self.api_mode == "mongodb" else self._db.get_container_client(collection)
        documents = []
        
        for doc_id in ids:
            try:
                if self.api_mode == "mongodb":
                    doc = coll.find_one({"_id": doc_id})
                else:
                    doc = coll.read_item(item=doc_id, partition_key=doc_id)
                
                if doc:
                    documents.append(KnowledgeDocument(
                        id=str(doc.get("_id" if self.api_mode == "mongodb" else "id", "")),
                        content=doc.get(self.text_field, ""),
                        embedding=doc.get(self.embedding_field),
                        metadata=doc.get("metadata"),
                        content_hash=doc.get("content_hash"),
                        created_at=doc.get("created_at", 0)
                    ))
            except Exception as e:
                logger.warning(f"Failed to get {doc_id}: {e}")
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        self._init_client()
        
        coll = self._db[collection] if self.api_mode == "mongodb" else self._db.get_container_client(collection)
        
        if ids:
            count = 0
            for doc_id in ids:
                try:
                    if self.api_mode == "mongodb":
                        coll.delete_one({"_id": doc_id})
                    else:
                        coll.delete_item(item=doc_id, partition_key=doc_id)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {doc_id}: {e}")
            return count
        
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        self._init_client()
        
        if self.api_mode == "mongodb":
            return self._db[collection].count_documents({})
        else:
            # SQL API count
            coll = self._db.get_container_client(collection)
            result = list(coll.query_items(
                query="SELECT VALUE COUNT(1) FROM c",
                enable_cross_partition_query=True
            ))
            return result[0] if result else 0
    
    def close(self) -> None:
        """Close the connection."""
        if self._client:
            if self.api_mode == "mongodb":
                self._client.close()
            self._client = None
            self._db = None
            self._collection = None
            self._initialized = False
