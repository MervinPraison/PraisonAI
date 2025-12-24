"""
Redis Vector implementation of KnowledgeStore.

Requires: redis
Install: pip install redis
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument

logger = logging.getLogger(__name__)


class RedisVectorKnowledgeStore(KnowledgeStore):
    """
    Redis-based knowledge store using RediSearch for vector search.
    
    Requires Redis Stack or Redis with RediSearch module.
    
    Example:
        store = RedisVectorKnowledgeStore(
            url="redis://localhost:6379"
        )
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 6379,
        password: Optional[str] = None,
        prefix: str = "praison:vec:",
    ):
        try:
            import redis
            from redis.commands.search.field import VectorField, TextField, NumericField
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType
            from redis.commands.search.query import Query
        except ImportError:
            raise ImportError(
                "redis is required for Redis Vector support. "
                "Install with: pip install redis"
            )
        
        self._redis = redis
        self._VectorField = VectorField
        self._TextField = TextField
        self._NumericField = NumericField
        self._IndexDefinition = IndexDefinition
        self._IndexType = IndexType
        self._Query = Query
        
        self.prefix = prefix
        
        if url:
            self._client = redis.from_url(url, decode_responses=False)
        else:
            self._client = redis.Redis(
                host=host, port=port, password=password, decode_responses=False
            )
        
        self._client.ping()
        logger.info(f"Connected to Redis at {url or f'{host}:{port}'}")
    
    def _index_name(self, collection: str) -> str:
        return f"{self.prefix}{collection}:idx"
    
    def _doc_key(self, collection: str, doc_id: str) -> str:
        return f"{self.prefix}{collection}:{doc_id}"
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new index."""
        index_name = self._index_name(name)
        
        distance_map = {"cosine": "COSINE", "euclidean": "L2", "dot": "IP"}
        
        schema = (
            self._TextField("content"),
            self._TextField("content_hash"),
            self._NumericField("created_at"),
            self._VectorField(
                "embedding",
                "HNSW",
                {
                    "TYPE": "FLOAT32",
                    "DIM": dimension,
                    "DISTANCE_METRIC": distance_map.get(distance, "COSINE"),
                }
            ),
        )
        
        definition = self._IndexDefinition(
            prefix=[f"{self.prefix}{name}:"],
            index_type=self._IndexType.HASH,
        )
        
        try:
            self._client.ft(index_name).create_index(schema, definition=definition)
            logger.info(f"Created Redis index: {index_name}")
        except Exception as e:
            if "Index already exists" not in str(e):
                raise
    
    def delete_collection(self, name: str) -> bool:
        """Delete an index and all documents."""
        index_name = self._index_name(name)
        try:
            self._client.ft(index_name).dropindex(delete_documents=True)
            return True
        except Exception as e:
            logger.warning(f"Failed to delete index {index_name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if an index exists."""
        index_name = self._index_name(name)
        try:
            self._client.ft(index_name).info()
            return True
        except Exception:
            return False
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        try:
            indexes = self._client.execute_command("FT._LIST")
            prefix = f"{self.prefix}"
            return [
                idx.decode().replace(prefix, "").replace(":idx", "")
                for idx in indexes
                if idx.decode().startswith(prefix)
            ]
        except Exception:
            return []
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        import numpy as np
        
        ids = []
        pipe = self._client.pipeline()
        
        for doc in documents:
            if doc.embedding is None:
                raise ValueError(f"Document {doc.id} has no embedding")
            
            key = self._doc_key(collection, doc.id)
            embedding_bytes = np.array(doc.embedding, dtype=np.float32).tobytes()
            
            pipe.hset(key, mapping={
                "content": doc.content,
                "content_hash": doc.content_hash or "",
                "created_at": doc.created_at,
                "embedding": embedding_bytes,
            })
            ids.append(doc.id)
        
        pipe.execute()
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
        import numpy as np
        
        index_name = self._index_name(collection)
        query_bytes = np.array(query_embedding, dtype=np.float32).tobytes()
        
        query_str = f"*=>[KNN {limit} @embedding $vec AS score]"
        
        query = (
            self._Query(query_str)
            .return_fields("content", "content_hash", "created_at", "score")
            .sort_by("score")
            .dialect(2)
        )
        
        results = self._client.ft(index_name).search(
            query, query_params={"vec": query_bytes}
        )
        
        documents = []
        for doc in results.docs:
            score = float(doc.score) if hasattr(doc, "score") else 0
            # Redis returns distance, convert to similarity for cosine
            similarity = 1 - score
            
            if score_threshold and similarity < score_threshold:
                continue
            
            doc_id = doc.id.decode() if isinstance(doc.id, bytes) else doc.id
            doc_id = doc_id.split(":")[-1]  # Remove prefix
            
            knowledge_doc = KnowledgeDocument(
                id=doc_id,
                content=doc.content.decode() if isinstance(doc.content, bytes) else doc.content,
                embedding=None,
                metadata={},
                content_hash=doc.content_hash.decode() if isinstance(doc.content_hash, bytes) else doc.content_hash,
                created_at=float(doc.created_at) if doc.created_at else 0,
            )
            documents.append(knowledge_doc)
        
        return documents
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        import numpy as np
        
        documents = []
        for doc_id in ids:
            key = self._doc_key(collection, doc_id)
            data = self._client.hgetall(key)
            
            if data:
                embedding = None
                if b"embedding" in data:
                    embedding = np.frombuffer(data[b"embedding"], dtype=np.float32).tolist()
                
                doc = KnowledgeDocument(
                    id=doc_id,
                    content=data.get(b"content", b"").decode(),
                    embedding=embedding,
                    metadata={},
                    content_hash=data.get(b"content_hash", b"").decode(),
                    created_at=float(data.get(b"created_at", 0)),
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
        if ids:
            pipe = self._client.pipeline()
            for doc_id in ids:
                key = self._doc_key(collection, doc_id)
                pipe.delete(key)
            pipe.execute()
            return len(ids)
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        index_name = self._index_name(collection)
        try:
            info = self._client.ft(index_name).info()
            return int(info.get("num_docs", 0))
        except Exception:
            return 0
    
    def close(self) -> None:
        """Close the store."""
        if self._client:
            self._client.close()
