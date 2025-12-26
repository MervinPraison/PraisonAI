"""
Upstash Vector implementation of KnowledgeStore.

Requires: upstash-vector
Install: pip install upstash-vector
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class UpstashVectorKnowledgeStore(KnowledgeStore):
    """
    Upstash Vector store for knowledge/RAG.
    
    Uses Upstash's serverless vector database.
    
    Example:
        store = UpstashVectorKnowledgeStore(
            url="https://xxx.upstash.io",
            token="your-token"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        embedding_dim: int = 1536,
    ):
        """
        Initialize Upstash Vector store.
        
        Args:
            url: Upstash Vector REST URL (or UPSTASH_VECTOR_REST_URL env)
            token: Upstash Vector REST token (or UPSTASH_VECTOR_REST_TOKEN env)
            embedding_dim: Embedding dimension
        """
        self.url = url or os.getenv("UPSTASH_VECTOR_REST_URL")
        self.token = token or os.getenv("UPSTASH_VECTOR_REST_TOKEN")
        self.embedding_dim = embedding_dim
        
        self._index = None
        self._initialized = False
    
    def _init_client(self):
        """Initialize Upstash client lazily."""
        if self._initialized:
            return
        
        if not self.url or not self.token:
            raise ValueError(
                "Upstash Vector requires url and token. "
                "Set UPSTASH_VECTOR_REST_URL and UPSTASH_VECTOR_REST_TOKEN env vars."
            )
        
        try:
            from upstash_vector import Index
        except ImportError:
            raise ImportError(
                "upstash-vector is required for Upstash Vector support. "
                "Install with: pip install upstash-vector"
            )
        
        self._index = Index(url=self.url, token=self.token)
        self._initialized = True
    
    def create_collection(
        self,
        name: str,
        dimension: int = 1536,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create collection (Upstash uses namespaces)."""
        self._init_client()
        # Upstash Vector uses a single index with namespaces
        logger.info(f"Using namespace '{name}' in Upstash Vector index")
    
    def delete_collection(self, name: str) -> bool:
        """Delete all vectors in namespace."""
        self._init_client()
        try:
            self._index.delete_namespace(name)
            return True
        except Exception as e:
            logger.error(f"Failed to delete namespace {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if namespace has vectors."""
        self._init_client()
        try:
            info = self._index.info()
            namespaces = info.namespaces if hasattr(info, 'namespaces') else {}
            return name in namespaces
        except Exception:
            return False
    
    def list_collections(self) -> List[str]:
        """List all namespaces."""
        self._init_client()
        try:
            info = self._index.info()
            namespaces = info.namespaces if hasattr(info, 'namespaces') else {}
            return list(namespaces.keys())
        except Exception as e:
            logger.error(f"Failed to list namespaces: {e}")
            return []
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        self._init_client()
        
        vectors = []
        for doc in documents:
            if not doc.embedding:
                logger.warning(f"Document {doc.id} has no embedding, skipping")
                continue
            
            vectors.append({
                "id": doc.id,
                "vector": doc.embedding,
                "metadata": {
                    "content": doc.content,
                    **(doc.metadata or {}),
                    "content_hash": doc.content_hash,
                    "created_at": doc.created_at,
                }
            })
        
        if vectors:
            self._index.upsert(vectors, namespace=collection)
        
        return [v["id"] for v in vectors]
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Upsert documents (same as insert for Upstash)."""
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
        self._init_client()
        
        try:
            results = self._index.query(
                vector=query_embedding,
                top_k=limit,
                include_metadata=True,
                namespace=collection,
                filter=filters
            )
            
            documents = []
            for result in results:
                score = result.score if hasattr(result, 'score') else 0
                if score_threshold and score < score_threshold:
                    continue
                
                metadata = result.metadata if hasattr(result, 'metadata') else {}
                content = metadata.pop("content", "") if metadata else ""
                
                documents.append(KnowledgeDocument(
                    id=result.id,
                    content=content,
                    metadata={**metadata, "score": score},
                    content_hash=metadata.get("content_hash") if metadata else None,
                    created_at=metadata.get("created_at", 0) if metadata else 0
                ))
            
            return documents
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        self._init_client()
        
        documents = []
        try:
            results = self._index.fetch(ids, include_metadata=True, namespace=collection)
            
            for result in results:
                if result:
                    metadata = result.metadata if hasattr(result, 'metadata') else {}
                    content = metadata.pop("content", "") if metadata else ""
                    
                    documents.append(KnowledgeDocument(
                        id=result.id,
                        content=content,
                        embedding=result.vector if hasattr(result, 'vector') else None,
                        metadata=metadata,
                        content_hash=metadata.get("content_hash") if metadata else None,
                        created_at=metadata.get("created_at", 0) if metadata else 0
                    ))
        except Exception as e:
            logger.error(f"Fetch failed: {e}")
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        self._init_client()
        
        try:
            if ids:
                self._index.delete(ids, namespace=collection)
                return len(ids)
            elif filters:
                # Upstash doesn't support filter-based delete directly
                logger.warning("Filter-based delete not supported, use IDs")
                return 0
            else:
                self._index.delete_namespace(collection)
                return -1  # Unknown count
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return 0
    
    def count(self, collection: str) -> int:
        """Count documents in namespace."""
        self._init_client()
        
        try:
            info = self._index.info()
            namespaces = info.namespaces if hasattr(info, 'namespaces') else {}
            ns_info = namespaces.get(collection, {})
            return ns_info.get("vector_count", 0) if isinstance(ns_info, dict) else 0
        except Exception as e:
            logger.error(f"Count failed: {e}")
            return 0
    
    def close(self) -> None:
        """Close the client."""
        self._index = None
        self._initialized = False
