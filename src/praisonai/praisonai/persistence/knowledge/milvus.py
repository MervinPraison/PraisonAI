"""
Milvus implementation of KnowledgeStore.

Requires: pymilvus
Install: pip install pymilvus
"""

import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class MilvusKnowledgeStore(KnowledgeStore):
    """
    Milvus-based knowledge store for vector search.
    
    Example:
        store = MilvusKnowledgeStore(
            host="localhost",
            port=19530
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 19530,
        token: Optional[str] = None,
        db_name: str = "default",
    ):
        try:
            from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType, utility
        except ImportError:
            raise ImportError(
                "pymilvus is required for Milvus support. "
                "Install with: pip install pymilvus"
            )
        
        self._pymilvus = {
            "connections": connections,
            "Collection": Collection,
            "FieldSchema": FieldSchema,
            "CollectionSchema": CollectionSchema,
            "DataType": DataType,
            "utility": utility,
        }
        
        if url:
            # Parse milvus://host:port
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or host
            port = parsed.port or port
        
        connections.connect(
            alias="default",
            host=host,
            port=port,
            token=token,
            db_name=db_name,
        )
        logger.info(f"Connected to Milvus at {host}:{port}")
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new collection."""
        FieldSchema = self._pymilvus["FieldSchema"]
        CollectionSchema = self._pymilvus["CollectionSchema"]
        DataType = self._pymilvus["DataType"]
        Collection = self._pymilvus["Collection"]
        
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=256),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="content_hash", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="created_at", dtype=DataType.DOUBLE),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dimension),
        ]
        
        schema = CollectionSchema(fields=fields, description="PraisonAI knowledge store")
        collection = Collection(name=name, schema=schema)
        
        # Create index
        metric_map = {"cosine": "COSINE", "euclidean": "L2", "dot": "IP"}
        index_params = {
            "metric_type": metric_map.get(distance, "COSINE"),
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256}
        }
        collection.create_index(field_name="vector", index_params=index_params)
        logger.info(f"Created Milvus collection: {name}")
    
    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        utility = self._pymilvus["utility"]
        try:
            utility.drop_collection(name)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete collection {name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        utility = self._pymilvus["utility"]
        return utility.has_collection(name)
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        utility = self._pymilvus["utility"]
        return utility.list_collections()
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        Collection = self._pymilvus["Collection"]
        col = Collection(collection)
        col.load()
        
        data = [
            [doc.id for doc in documents],
            [doc.content for doc in documents],
            [doc.content_hash or "" for doc in documents],
            [doc.created_at for doc in documents],
            [doc.embedding for doc in documents],
        ]
        
        col.insert(data)
        col.flush()
        return [doc.id for doc in documents]
    
    def upsert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents."""
        Collection = self._pymilvus["Collection"]
        col = Collection(collection)
        col.load()
        
        data = [
            [doc.id for doc in documents],
            [doc.content for doc in documents],
            [doc.content_hash or "" for doc in documents],
            [doc.created_at for doc in documents],
            [doc.embedding for doc in documents],
        ]
        
        col.upsert(data)
        col.flush()
        return [doc.id for doc in documents]
    
    def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents."""
        Collection = self._pymilvus["Collection"]
        col = Collection(collection)
        col.load()
        
        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}
        
        expr = None
        if filters:
            conditions = [f'{k} == "{v}"' for k, v in filters.items()]
            expr = " and ".join(conditions)
        
        results = col.search(
            data=[query_embedding],
            anns_field="vector",
            param=search_params,
            limit=limit,
            expr=expr,
            output_fields=["id", "content", "content_hash", "created_at"],
        )
        
        documents = []
        for hits in results:
            for hit in hits:
                if score_threshold and hit.score < score_threshold:
                    continue
                
                doc = KnowledgeDocument(
                    id=hit.entity.get("id"),
                    content=hit.entity.get("content", ""),
                    embedding=None,
                    metadata={},
                    content_hash=hit.entity.get("content_hash"),
                    created_at=hit.entity.get("created_at", 0),
                )
                documents.append(doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        Collection = self._pymilvus["Collection"]
        col = Collection(collection)
        col.load()
        
        id_list = ", ".join([f'"{i}"' for i in ids])
        expr = f"id in [{id_list}]"
        
        results = col.query(
            expr=expr,
            output_fields=["id", "content", "content_hash", "created_at", "vector"],
        )
        
        documents = []
        for row in results:
            doc = KnowledgeDocument(
                id=row["id"],
                content=row.get("content", ""),
                embedding=row.get("vector"),
                metadata={},
                content_hash=row.get("content_hash"),
                created_at=row.get("created_at", 0),
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
        Collection = self._pymilvus["Collection"]
        col = Collection(collection)
        col.load()
        
        if ids:
            id_list = ", ".join([f'"{i}"' for i in ids])
            expr = f"id in [{id_list}]"
            col.delete(expr)
            return len(ids)
        elif filters:
            conditions = [f'{k} == "{v}"' for k, v in filters.items()]
            expr = " and ".join(conditions)
            col.delete(expr)
            return -1
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        Collection = self._pymilvus["Collection"]
        col = Collection(collection)
        return col.num_entities
    
    def close(self) -> None:
        """Close the store."""
        connections = self._pymilvus["connections"]
        connections.disconnect("default")
