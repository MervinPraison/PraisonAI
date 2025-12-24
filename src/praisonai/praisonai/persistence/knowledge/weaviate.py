"""
Weaviate implementation of KnowledgeStore.

Requires: weaviate-client
Install: pip install weaviate-client
"""

import logging
import os
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class WeaviateKnowledgeStore(KnowledgeStore):
    """
    Weaviate-based knowledge store for vector search.
    
    Example:
        store = WeaviateKnowledgeStore(
            url="http://localhost:8080"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        additional_headers: Optional[Dict[str, str]] = None,
    ):
        try:
            import weaviate
        except ImportError:
            raise ImportError(
                "weaviate-client is required for Weaviate support. "
                "Install with: pip install weaviate-client"
            )
        
        url = url or os.getenv("WEAVIATE_URL", "http://localhost:8080")
        api_key = api_key or os.getenv("WEAVIATE_API_KEY")
        
        auth = weaviate.auth.AuthApiKey(api_key) if api_key else None
        self._client = weaviate.connect_to_custom(
            http_host=url.replace("http://", "").replace("https://", "").split(":")[0],
            http_port=int(url.split(":")[-1]) if ":" in url.split("/")[-1] else 8080,
            http_secure=url.startswith("https"),
            auth_credentials=auth,
            additional_headers=additional_headers,
        )
        logger.info(f"Connected to Weaviate at {url}")
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new collection (class in Weaviate)."""
        from weaviate.classes.config import Configure, Property, DataType
        
        distance_map = {"cosine": "cosine", "euclidean": "l2-squared", "dot": "dot"}
        
        self._client.collections.create(
            name=name,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=distance_map.get(distance, "cosine")
            ),
            properties=[
                Property(name="content", data_type=DataType.TEXT),
                Property(name="content_hash", data_type=DataType.TEXT),
                Property(name="created_at", data_type=DataType.NUMBER),
            ]
        )
        logger.info(f"Created Weaviate collection: {name}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        try:
            self._client.collections.delete(name)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete collection {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        return self._client.collections.exists(name)
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        return [c.name for c in self._client.collections.list_all().values()]
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        col = self._client.collections.get(collection)
        ids = []
        
        with col.batch.dynamic() as batch:
            for doc in documents:
                if doc.embedding is None:
                    raise ValueError(f"Document {doc.id} has no embedding")
                
                properties = {
                    "content": doc.content,
                    "content_hash": doc.content_hash or "",
                    "created_at": doc.created_at,
                    **(doc.metadata or {})
                }
                
                batch.add_object(
                    properties=properties,
                    vector=doc.embedding,
                    uuid=doc.id,
                )
                ids.append(doc.id)
        
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
        col = self._client.collections.get(collection)
        
        query = col.query.near_vector(
            near_vector=query_embedding,
            limit=limit,
            return_metadata=["distance"],
        )
        
        documents = []
        for obj in query.objects:
            if score_threshold:
                score = 1 - (obj.metadata.distance or 0)
                if score < score_threshold:
                    continue
            
            props = obj.properties
            doc = KnowledgeDocument(
                id=str(obj.uuid),
                content=props.get("content", ""),
                embedding=None,
                metadata={k: v for k, v in props.items() if k not in ("content", "content_hash", "created_at")},
                content_hash=props.get("content_hash"),
                created_at=props.get("created_at", 0),
            )
            documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        col = self._client.collections.get(collection)
        documents = []
        
        for doc_id in ids:
            try:
                obj = col.query.fetch_object_by_id(doc_id, include_vector=True)
                if obj:
                    props = obj.properties
                    doc = KnowledgeDocument(
                        id=str(obj.uuid),
                        content=props.get("content", ""),
                        embedding=list(obj.vector) if obj.vector else None,
                        metadata={k: v for k, v in props.items() if k not in ("content", "content_hash", "created_at")},
                        content_hash=props.get("content_hash"),
                        created_at=props.get("created_at", 0),
                    )
                    documents.append(doc)
            except Exception:
                pass
        
        return documents
    
    def delete(
        self,
        collection: str,
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents."""
        col = self._client.collections.get(collection)
        
        if ids:
            for doc_id in ids:
                col.data.delete_by_id(doc_id)
            return len(ids)
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        col = self._client.collections.get(collection)
        return col.aggregate.over_all(total_count=True).total_count or 0
    
    def close(self) -> None:
        """Close the store."""
        if self._client:
            self._client.close()
