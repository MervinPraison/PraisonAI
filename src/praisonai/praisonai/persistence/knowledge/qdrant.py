"""
Qdrant implementation of KnowledgeStore.

Requires: qdrant-client
Install: pip install qdrant-client
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class QdrantKnowledgeStore(KnowledgeStore):
    """
    Qdrant-based knowledge store for vector search.
    
    Example:
        store = QdrantKnowledgeStore(
            url="http://localhost:6333"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 6333,
        grpc_port: int = 6334,
        api_key: Optional[str] = None,
        prefer_grpc: bool = False,
        timeout: int = 30,
    ):
        """
        Initialize Qdrant knowledge store.
        
        Args:
            url: Full URL (overrides host/port)
            host: Qdrant host
            port: Qdrant HTTP port
            grpc_port: Qdrant gRPC port
            api_key: API key for Qdrant Cloud
            prefer_grpc: Use gRPC instead of HTTP
            timeout: Request timeout in seconds
        """
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import (
                Distance, VectorParams, PointStruct,
                Filter, FieldCondition, MatchValue
            )
        except ImportError:
            raise ImportError(
                "qdrant-client is required for Qdrant support. "
                "Install with: pip install qdrant-client"
            )
        
        self._QdrantClient = QdrantClient
        self._Distance = Distance
        self._VectorParams = VectorParams
        self._PointStruct = PointStruct
        self._Filter = Filter
        self._FieldCondition = FieldCondition
        self._MatchValue = MatchValue
        
        if url:
            self._client = QdrantClient(url=url, api_key=api_key, timeout=timeout)
        else:
            self._client = QdrantClient(
                host=host,
                port=port,
                grpc_port=grpc_port,
                api_key=api_key,
                prefer_grpc=prefer_grpc,
                timeout=timeout,
            )
        
        logger.info(f"Connected to Qdrant at {url or f'{host}:{port}'}")
    
    def _get_distance(self, distance: str) -> Any:
        """Convert distance string to Qdrant Distance enum."""
        distance_map = {
            "cosine": self._Distance.COSINE,
            "euclidean": self._Distance.EUCLID,
            "dot": self._Distance.DOT,
            "manhattan": self._Distance.MANHATTAN,
        }
        return distance_map.get(distance.lower(), self._Distance.COSINE)
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new collection."""
        self._client.create_collection(
            collection_name=name,
            vectors_config=self._VectorParams(
                size=dimension,
                distance=self._get_distance(distance)
            )
        )
        logger.info(f"Created Qdrant collection: {name} (dim={dimension}, distance={distance})")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        try:
            self._client.delete_collection(collection_name=name)
            logger.info(f"Deleted Qdrant collection: {name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete collection {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        try:
            collections = self._client.get_collections()
            return any(c.name == name for c in collections.collections)
        except Exception:
            return False
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        collections = self._client.get_collections()
        return [c.name for c in collections.collections]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents into a collection."""
        points = []
        ids = []
        
        for i, doc in enumerate(documents):
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            
            point = self._PointStruct(
                id=i,  # Qdrant prefers numeric IDs for performance
                vector=doc.embedding,
                payload={
                    "doc_id": doc.id,
                    "content": doc.content,
                    "content_hash": doc.content_hash,
                    "created_at": doc.created_at,
                    **(doc.metadata or {})
                }
            )
            points.append(point)
            ids.append(doc.id)
        
        self._client.upsert(collection_name=collection, points=points)
        logger.debug(f"Inserted {len(documents)} documents into {collection}")
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
        search_filter = None
        if filters:
            conditions = [
                self._FieldCondition(
                    key=k,
                    match=self._MatchValue(value=v)
                )
                for k, v in filters.items()
            ]
            search_filter = self._Filter(must=conditions)
        
        results = self._client.query_points(
            collection_name=collection,
            query=query_embedding,
            limit=limit,
            query_filter=search_filter,
            score_threshold=score_threshold,
        )
        
        documents = []
        for point in results.points:
            payload = point.payload or {}
            doc = KnowledgeDocument(
                id=payload.get("doc_id", str(point.id)),
                content=payload.get("content", ""),
                embedding=None,  # Don't return embeddings by default
                metadata={
                    k: v for k, v in payload.items()
                    if k not in ("doc_id", "content", "content_hash", "created_at")
                },
                content_hash=payload.get("content_hash"),
                created_at=payload.get("created_at", 0),
            )
            documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        # Qdrant uses numeric IDs internally, so we search by doc_id in payload
        documents = []
        for doc_id in ids:
            results = self._client.scroll(
                collection_name=collection,
                scroll_filter=self._Filter(
                    must=[
                        self._FieldCondition(
                            key="doc_id",
                            match=self._MatchValue(value=doc_id)
                        )
                    ]
                ),
                limit=1,
            )
            for point in results[0]:
                payload = point.payload or {}
                doc = KnowledgeDocument(
                    id=payload.get("doc_id", str(point.id)),
                    content=payload.get("content", ""),
                    embedding=list(point.vector) if point.vector else None,
                    metadata={
                        k: v for k, v in payload.items()
                        if k not in ("doc_id", "content", "content_hash", "created_at")
                    },
                    content_hash=payload.get("content_hash"),
                    created_at=payload.get("created_at", 0),
                )
                documents.append(doc)
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents by IDs or filters."""
        if ids:
            # Delete by doc_id in payload
            for doc_id in ids:
                self._client.delete(
                    collection_name=collection,
                    points_selector=self._Filter(
                        must=[
                            self._FieldCondition(
                                key="doc_id",
                                match=self._MatchValue(value=doc_id)
                            )
                        ]
                    )
                )
            return len(ids)
        elif filters:
            conditions = [
                self._FieldCondition(
                    key=k,
                    match=self._MatchValue(value=v)
                )
                for k, v in filters.items()
            ]
            self._client.delete(
                collection_name=collection,
                points_selector=self._Filter(must=conditions)
            )
            return -1  # Unknown count
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents in a collection."""
        info = self._client.get_collection(collection_name=collection)
        return info.points_count or 0
    
    def close(self) -> None:
        """Close the store."""
        if self._client:
            self._client.close()
            self._client = None
