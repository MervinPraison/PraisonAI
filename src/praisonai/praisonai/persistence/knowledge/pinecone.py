"""
Pinecone implementation of KnowledgeStore.

Requires: pinecone-client
Install: pip install pinecone-client
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class PineconeKnowledgeStore(KnowledgeStore):
    """
    Pinecone-based knowledge store for vector search.
    
    Cloud-only managed vector database.
    
    Example:
        store = PineconeKnowledgeStore(
            api_key="your-api-key",
            index_name="praisonai"
        )
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
        environment: Optional[str] = None,
        namespace: str = "",
    ):
        try:
            from pinecone import Pinecone
        except ImportError:
            raise ImportError(
                "pinecone-client is required for Pinecone support. "
                "Install with: pip install pinecone-client"
            )
        
        api_key = api_key or os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError("Pinecone API key is required")
        
        self._pc = Pinecone(api_key=api_key)
        self._index_name = index_name or os.getenv("PINECONE_INDEX", "praisonai")
        self._namespace = namespace
        self._index = None
        
        # Try to connect to existing index
        try:
            self._index = self._pc.Index(self._index_name)
            logger.info(f"Connected to Pinecone index: {self._index_name}")
        except Exception as e:
            logger.warning(f"Index {self._index_name} not found: {e}")
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new index (Pinecone calls them indexes, not collections)."""
        from pinecone import ServerlessSpec
        
        metric_map = {"cosine": "cosine", "euclidean": "euclidean", "dot": "dotproduct"}
        
        self._pc.create_index(
            name=name,
            dimension=dimension,
            metric=metric_map.get(distance, "cosine"),
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        self._index_name = name
        self._index = self._pc.Index(name)
        logger.info(f"Created Pinecone index: {name}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete an index."""
        try:
            self._pc.delete_index(name)
            if name == self._index_name:
                self._index = None
            return True
        except Exception as e:
            logger.warning(f"Failed to delete index {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if an index exists."""
        try:
            indexes = self._pc.list_indexes()
            return any(idx.name == name for idx in indexes)
        except Exception:
            return False
    
    def list_collections(self) -> List[str]:
        """List all indexes."""
        indexes = self._pc.list_indexes()
        return [idx.name for idx in indexes]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        if collection != self._index_name:
            self._index = self._pc.Index(collection)
            self._index_name = collection
        
        vectors = []
        ids = []
        
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            
            vectors.append({
                "id": doc.id,
                "values": doc.embedding,
                "metadata": {
                    "content": doc.content,
                    "content_hash": doc.content_hash or "",
                    "created_at": doc.created_at,
                    **(doc.metadata or {})
                }
            })
            ids.append(doc.id)
        
        self._index.upsert(vectors=vectors, namespace=self._namespace)
        return ids
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents."""
        return self.insert(collection, documents)
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents."""
        if collection != self._index_name:
            self._index = self._pc.Index(collection)
            self._index_name = collection
        
        results = self._index.query(
            vector=query_embedding,
            top_k=limit,
            filter=filters,
            include_metadata=True,
            namespace=self._namespace,
        )
        
        documents = []
        for match in results.matches:
            if score_threshold and match.score < score_threshold:
                continue
            
            metadata = match.metadata or {}
            content = metadata.pop("content", "")
            content_hash = metadata.pop("content_hash", None)
            created_at = metadata.pop("created_at", 0)
            
            doc = KnowledgeDocument(
                id=match.id,
                content=content,
                embedding=None,
                metadata=metadata,
                content_hash=content_hash,
                created_at=created_at,
            )
            documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        if collection != self._index_name:
            self._index = self._pc.Index(collection)
            self._index_name = collection
        
        results = self._index.fetch(ids=ids, namespace=self._namespace)
        
        documents = []
        for doc_id, vector in results.vectors.items():
            metadata = vector.metadata or {}
            content = metadata.pop("content", "")
            content_hash = metadata.pop("content_hash", None)
            created_at = metadata.pop("created_at", 0)
            
            doc = KnowledgeDocument(
                id=doc_id,
                content=content,
                embedding=list(vector.values),
                metadata=metadata,
                content_hash=content_hash,
                created_at=created_at,
            )
            documents.append(doc)
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        if collection != self._index_name:
            self._index = self._pc.Index(collection)
            self._index_name = collection
        
        if ids:
            self._index.delete(ids=ids, namespace=self._namespace)
            return len(ids)
        elif filters:
            self._index.delete(filter=filters, namespace=self._namespace)
            return -1
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        if collection != self._index_name:
            self._index = self._pc.Index(collection)
            self._index_name = collection
        
        stats = self._index.describe_index_stats()
        if self._namespace:
            return stats.namespaces.get(self._namespace, {}).get("vector_count", 0)
        return stats.total_vector_count
    
    def close(self) -> None:
        """Close the store."""
        self._index = None
