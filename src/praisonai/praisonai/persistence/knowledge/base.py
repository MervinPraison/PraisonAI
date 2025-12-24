"""
Base interfaces for KnowledgeStore.

KnowledgeStore handles vector embeddings and semantic search for RAG.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import uuid
import hashlib


@dataclass
class KnowledgeDocument:
    """A document with vector embedding for semantic search."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    content_hash: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        if self.content and not self.content_hash:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding,
            "metadata": self.metadata,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeDocument":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class KnowledgeStore(ABC):
    """
    Abstract base class for vector/knowledge persistence.
    
    Implementations handle document storage and semantic search for different backends:
    - Qdrant, Pinecone, ChromaDB, Weaviate (dedicated vector DBs)
    - LanceDB, Milvus (embedded/distributed vector DBs)
    - PGVector, Redis, Cassandra, ClickHouse (vector extensions)
    """
    
    @abstractmethod
    def create_collection(
        self, 
        name: str, 
        dimension: int,
        distance: str = "cosine",
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Create a new collection/index for vectors."""
        raise NotImplementedError
    
    @abstractmethod
    def delete_collection(self, name: str) -> bool:
        """Delete a collection and all its documents."""
        raise NotImplementedError
    
    @abstractmethod
    def collection_exists(self, name: str) -> bool:
        """Check if a collection exists."""
        raise NotImplementedError
    
    @abstractmethod
    def list_collections(self) -> List[str]:
        """List all collections."""
        raise NotImplementedError
    
    @abstractmethod
    def insert(
        self, 
        collection: str, 
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert documents into a collection. Returns list of IDs."""
        raise NotImplementedError
    
    @abstractmethod
    def upsert(
        self, 
        collection: str, 
        documents: List[KnowledgeDocument]
    ) -> List[str]:
        """Insert or update documents. Returns list of IDs."""
        raise NotImplementedError
    
    @abstractmethod
    def search(
        self, 
        collection: str, 
        query_embedding: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: Optional[float] = None
    ) -> List[KnowledgeDocument]:
        """Search for similar documents by embedding."""
        raise NotImplementedError
    
    @abstractmethod
    def get(
        self, 
        collection: str, 
        ids: List[str]
    ) -> List[KnowledgeDocument]:
        """Get documents by IDs."""
        raise NotImplementedError
    
    @abstractmethod
    def delete(
        self, 
        collection: str, 
        ids: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """Delete documents by IDs or filters. Returns count deleted."""
        raise NotImplementedError
    
    @abstractmethod
    def count(self, collection: str) -> int:
        """Count documents in a collection."""
        raise NotImplementedError
    
    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""
        raise NotImplementedError
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
