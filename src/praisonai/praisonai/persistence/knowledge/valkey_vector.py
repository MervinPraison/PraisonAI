"""
Valkey Vector implementation of KnowledgeStore.

Uses ValkeySearch for vector indexing and semantic search.

Requires: valkey-glide-sync
Install: pip install 'praisonai[valkey]'
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .base import KnowledgeStore, KnowledgeDocument, validate_identifier

logger = logging.getLogger(__name__)


def create_valkey_client(
    host: Optional[str] = None,
    port: Optional[int] = None,
    password: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Create a Valkey client with consistent configuration across modules.
    
    Args:
        host: Valkey host (default from VALKEY_HOST env var or "localhost")
        port: Valkey port (default from VALKEY_PORT env var or 6379)
        password: Valkey password (default from VALKEY_PASSWORD env var)
        **kwargs: Additional client configuration
    
    Returns:
        Configured Valkey client instance
    """
    try:
        from glide import GlideClient, NodeAddress
        from glide.config import GlideClientConfiguration
    except ImportError:
        raise ImportError(
            "valkey-glide-sync is required for Valkey support. "
            "Install with: pip install 'praisonai[valkey]' or pip install valkey-glide-sync>=2.3.1"
        )
    
    # Resolve connection parameters from env vars or defaults
    host = host or os.getenv("VALKEY_HOST", "localhost")
    port = port or int(os.getenv("VALKEY_PORT", "6379"))
    password = password or os.getenv("VALKEY_PASSWORD")
    
    # Build client configuration
    addresses = [NodeAddress(host, port)]
    
    config = GlideClientConfiguration(
        addresses=addresses,
        credentials={"password": password} if password else None,
        **kwargs
    )
    
    return GlideClient(config)


class ValkeyVectorKnowledgeStore(KnowledgeStore):
    """
    Valkey-based knowledge store using ValkeySearch for vector search.
    
    Requires Valkey with ValkeySearch module for vector indexing and search.
    
    Example:
        store = ValkeyVectorKnowledgeStore(
            host="localhost",
            port=6379,
            password="secret"
        )
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        prefix: str = "praison:vec:",
        **kwargs
    ):
        """
        Initialize Valkey vector knowledge store.
        
        Args:
            host: Valkey host (default from VALKEY_HOST env var or "localhost")
            port: Valkey port (default from VALKEY_PORT env var or 6379)
            password: Valkey password (default from VALKEY_PASSWORD env var)
            prefix: Key prefix for namespacing
            **kwargs: Additional client configuration
        """
        self.prefix = prefix
        self._client = create_valkey_client(host=host, port=port, password=password, **kwargs)
        
        try:
            self._client.ping()
            logger.info(f"Connected to Valkey at {host or 'localhost'}:{port or 6379}")
        except Exception as e:
            logger.error(f"Failed to connect to Valkey: {e}")
            raise
    
    def _index_name(self, collection: str) -> str:
        """Generate index name for collection."""
        return f"{self.prefix}{collection}:idx"
    
    def _doc_key(self, collection: str, doc_id: str) -> str:
        """Generate document key for collection and ID."""
        return f"{self.prefix}{collection}:{doc_id}"
    
    def create_collection(
        self,
        name: str,
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new vector index."""
        validate_identifier(name, "collection name")
        index_name = self._index_name(name)
        
        distance_map = {"cosine": "COSINE", "euclidean": "L2", "dot": "IP"}
        distance_metric = distance_map.get(distance, "COSINE")
        
        # Create ValkeySearch index using custom commands
        # Note: This uses the same pattern as RediSearch but for Valkey
        try:
            # Build FT.CREATE command for ValkeySearch
            cmd = [
                "FT.CREATE", index_name,
                "ON", "HASH",
                "PREFIX", "1", f"{self.prefix}{name}:",
                "SCHEMA",
                "content", "TEXT",
                "content_hash", "TEXT",
                "created_at", "NUMERIC",
                "embedding", "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", str(dimension),
                "DISTANCE_METRIC", distance_metric
            ]
            
            self._client.custom_command(cmd)
            logger.info(f"Created Valkey vector index: {index_name}")
        except Exception as e:
            if "Index already exists" not in str(e):
                logger.error(f"Failed to create index {index_name}: {e}")
                raise
    
    def delete_collection(self, name: str) -> bool:
        """Delete an index and all documents."""
        validate_identifier(name, "collection name")
        index_name = self._index_name(name)
        try:
            self._client.custom_command(["FT.DROPINDEX", index_name, "DD"])
            return True
        except Exception as e:
            logger.warning(f"Failed to delete index {index_name}: {e}")
            return False
    
    def collection_exists(self, name: str) -> bool:
        """Check if an index exists."""
        validate_identifier(name, "collection name")
        index_name = self._index_name(name)
        try:
            self._client.custom_command(["FT.INFO", index_name])
            return True
        except Exception:
            return False
    
    def list_collections(self) -> List[str]:
        """List all collections."""
        try:
            indexes = self._client.custom_command(["FT._LIST"])
            prefix = f"{self.prefix}"
            return [
                idx.replace(prefix, "").replace(":idx", "")
                for idx in indexes
                if idx.startswith(prefix) and idx.endswith(":idx")
            ]
        except Exception:
            return []
    
    def insert(
        self,
        collection: str,
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents."""
        validate_identifier(collection, "collection name")
        
        import numpy as np
        
        ids = []
        # Use pipeline for batch operations if available, otherwise iterate
        try:
            # Batch insert using pipeline-like approach
            for doc in documents:
                if doc.embedding is None:
                    raise ValueError(f"Document {doc.id} has no embedding")
                
                key = self._doc_key(collection, doc.id)
                embedding_bytes = np.array(doc.embedding, dtype=np.float32).tobytes()
                
                # Use hset to store document fields
                fields = {
                    "content": doc.content,
                    "content_hash": doc.content_hash or "",
                    "created_at": str(doc.created_at),
                    "embedding": embedding_bytes,
                }
                
                self._client.hset(key, fields)
                ids.append(doc.id)
                
        except Exception as e:
            logger.error(f"Failed to insert documents: {e}")
            raise
        
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
        validate_identifier(collection, "collection name")
        
        import numpy as np
        
        index_name = self._index_name(collection)
        query_bytes = np.array(query_embedding, dtype=np.float32).tobytes()
        
        # Build ValkeySearch query
        query_str = f"*=>[KNN {limit} @embedding $vec AS score]"
        
        try:
            # Execute ValkeySearch query
            cmd = [
                "FT.SEARCH", index_name, query_str,
                "PARAMS", "2", "vec", query_bytes,
                "RETURN", "4", "content", "content_hash", "created_at", "score",
                "SORTBY", "score",
                "DIALECT", "2"
            ]
            
            results = self._client.custom_command(cmd)
            
            documents = []
            # Parse results (results[0] is count, then pairs of [key, fields])
            if len(results) > 1:
                for i in range(1, len(results), 2):
                    if i + 1 < len(results):
                        doc_key = results[i]
                        fields = results[i + 1]
                        
                        # Convert fields list to dict
                        field_dict = {}
                        for j in range(0, len(fields), 2):
                            if j + 1 < len(fields):
                                field_dict[fields[j]] = fields[j + 1]
                        
                        score = float(field_dict.get("score", "0"))
                        # Valkey returns distance, convert to similarity for cosine
                        similarity = 1 - score
                        
                        if score_threshold and similarity < score_threshold:
                            continue
                        
                        doc_id = doc_key.split(":")[-1]  # Remove prefix
                        
                        knowledge_doc = KnowledgeDocument(
                            id=doc_id,
                            content=field_dict.get("content", ""),
                            embedding=None,  # Don't return embeddings in search
                            metadata={},
                            content_hash=field_dict.get("content_hash", ""),
                            created_at=float(field_dict.get("created_at", "0")),
                        )
                        documents.append(knowledge_doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Search failed for collection {collection}: {e}")
            return []
    
    def get(
        self,
        collection: str,
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        validate_identifier(collection, "collection name")
        
        import numpy as np
        
        documents = []
        for doc_id in ids:
            key = self._doc_key(collection, doc_id)
            data = self._client.hgetall(key)
            
            if data:
                embedding = None
                if "embedding" in data:
                    try:
                        embedding = np.frombuffer(data["embedding"], dtype=np.float32).tolist()
                    except Exception:
                        pass  # Skip invalid embeddings
                
                doc = KnowledgeDocument(
                    id=doc_id,
                    content=data.get("content", ""),
                    embedding=embedding,
                    metadata={},
                    content_hash=data.get("content_hash", ""),
                    created_at=float(data.get("created_at", 0)),
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
        validate_identifier(collection, "collection name")
        
        if ids:
            count = 0
            for doc_id in ids:
                key = self._doc_key(collection, doc_id)
                if self._client.delete([key]) > 0:
                    count += 1
            return count
        return 0
    
    def count(self, collection: str) -> int:
        """Count documents."""
        validate_identifier(collection, "collection name")
        index_name = self._index_name(collection)
        try:
            info = self._client.custom_command(["FT.INFO", index_name])
            # Parse info response to find num_docs
            for i, item in enumerate(info):
                if item == "num_docs" and i + 1 < len(info):
                    return int(info[i + 1])
            return 0
        except Exception:
            return 0
    
    def close(self) -> None:
        """Close the store."""
        if self._client:
            self._client.close()
            self._client = None