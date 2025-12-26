"""
Vector Store Adapter Protocol for PraisonAI Agents.

This module defines the protocol for vector stores and a registry system.
NO heavy imports - only stdlib and typing.

Implementations are provided by praisonai-tools or wrapper layer.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
import logging

logger = logging.getLogger(__name__)


@dataclass
class VectorRecord:
    """
    A record in a vector store.
    
    Attributes:
        id: Unique identifier
        text: The text content
        embedding: The vector embedding
        metadata: Optional metadata dict
        score: Optional similarity score (for query results)
    """
    id: str
    text: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "text": self.text,
            "embedding": self.embedding,
            "metadata": self.metadata,
            "score": self.score
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VectorRecord":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            text=data["text"],
            embedding=data["embedding"],
            metadata=data.get("metadata", {}),
            score=data.get("score")
        )


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """
    Protocol for vector stores.
    
    Implementations must provide methods for:
    - Adding vectors
    - Querying by vector similarity
    - Deleting vectors
    - Getting count
    """
    
    name: str
    
    def add(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None
    ) -> List[str]:
        """
        Add vectors to the store.
        
        Args:
            texts: List of text content
            embeddings: List of embedding vectors
            metadatas: Optional list of metadata dicts
            ids: Optional list of IDs (auto-generated if not provided)
            namespace: Optional namespace for multi-tenant isolation
            
        Returns:
            List of IDs for the added vectors
        """
        ...
    
    def query(
        self,
        embedding: List[float],
        top_k: int = 10,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[VectorRecord]:
        """
        Query vectors by similarity.
        
        Args:
            embedding: Query embedding vector
            top_k: Number of results to return
            namespace: Optional namespace filter
            filter: Optional metadata filter
            
        Returns:
            List of VectorRecord objects sorted by similarity
        """
        ...
    
    def delete(
        self,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        delete_all: bool = False
    ) -> int:
        """
        Delete vectors from the store.
        
        Args:
            ids: Optional list of IDs to delete
            namespace: Optional namespace filter
            filter: Optional metadata filter
            delete_all: If True, delete all vectors
            
        Returns:
            Number of vectors deleted
        """
        ...
    
    def count(self, namespace: Optional[str] = None) -> int:
        """
        Get the number of vectors in the store.
        
        Args:
            namespace: Optional namespace filter
            
        Returns:
            Number of vectors
        """
        ...
    
    def get(
        self,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> List[VectorRecord]:
        """
        Get vectors by ID.
        
        Args:
            ids: List of IDs to retrieve
            namespace: Optional namespace filter
            
        Returns:
            List of VectorRecord objects
        """
        ...


class VectorStoreRegistry:
    """
    Registry for vector stores.
    
    Provides lazy loading and configuration-based initialization.
    """
    
    _instance: Optional["VectorStoreRegistry"] = None
    
    def __new__(cls) -> "VectorStoreRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._stores: Dict[str, Callable[..., VectorStoreProtocol]] = {}
            cls._instance._initialized_stores: Dict[str, VectorStoreProtocol] = {}
        return cls._instance
    
    def register(
        self, 
        name: str, 
        factory: Callable[..., VectorStoreProtocol]
    ) -> None:
        """
        Register a vector store factory.
        
        Args:
            name: Unique name for the store (e.g., "chroma", "pinecone")
            factory: Callable that returns a VectorStoreProtocol instance
        """
        self._stores[name] = factory
    
    def get(
        self, 
        name: str, 
        config: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None
    ) -> Optional[VectorStoreProtocol]:
        """
        Get a vector store by name (lazy initialization).
        
        Args:
            name: Store name
            config: Optional configuration dict
            namespace: Optional namespace for multi-tenant isolation
            
        Returns:
            VectorStoreProtocol instance or None
        """
        cache_key = f"{name}:{namespace or 'default'}"
        
        if cache_key in self._initialized_stores:
            return self._initialized_stores[cache_key]
        
        if name in self._stores:
            try:
                store = self._stores[name](config=config, namespace=namespace)
                self._initialized_stores[cache_key] = store
                return store
            except Exception as e:
                logger.warning(f"Failed to initialize vector store '{name}': {e}")
                return None
        return None
    
    def list_stores(self) -> List[str]:
        """List all registered store names."""
        return list(self._stores.keys())
    
    def clear(self) -> None:
        """Clear all registered stores (mainly for testing)."""
        self._stores.clear()
        self._initialized_stores.clear()


def get_vector_store_registry() -> VectorStoreRegistry:
    """Get the global vector store registry instance."""
    return VectorStoreRegistry()


class InMemoryVectorStore:
    """
    Pure Python in-memory vector store for testing and default usage.
    
    Uses cosine similarity for queries. No external dependencies.
    """
    
    name: str = "memory"
    
    def __init__(
        self, 
        config: Optional[Dict[str, Any]] = None,
        namespace: Optional[str] = None
    ):
        self.config = config or {}
        self.default_namespace = namespace or "default"
        self._data: Dict[str, Dict[str, VectorRecord]] = {}  # namespace -> id -> record
    
    def _get_namespace_data(self, namespace: Optional[str] = None) -> Dict[str, VectorRecord]:
        """Get or create namespace data."""
        ns = namespace or self.default_namespace
        if ns not in self._data:
            self._data[ns] = {}
        return self._data[ns]
    
    def add(
        self,
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None
    ) -> List[str]:
        """Add vectors to the store."""
        import uuid
        
        ns_data = self._get_namespace_data(namespace)
        metadatas = metadatas or [{} for _ in texts]
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        
        result_ids = []
        for i, (text, embedding, metadata, id_) in enumerate(zip(texts, embeddings, metadatas, ids)):
            record = VectorRecord(
                id=id_,
                text=text,
                embedding=embedding,
                metadata=metadata
            )
            ns_data[id_] = record
            result_ids.append(id_)
        
        return result_ids
    
    def query(
        self,
        embedding: List[float],
        top_k: int = 10,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[VectorRecord]:
        """Query vectors by cosine similarity."""
        ns_data = self._get_namespace_data(namespace)
        
        if not ns_data:
            return []
        
        # Calculate cosine similarity for all records
        results = []
        for record in ns_data.values():
            # Apply metadata filter if provided
            if filter:
                match = True
                for key, value in filter.items():
                    if record.metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            score = self._cosine_similarity(embedding, record.embedding)
            results.append(VectorRecord(
                id=record.id,
                text=record.text,
                embedding=record.embedding,
                metadata=record.metadata,
                score=score
            ))
        
        # Sort by score descending and return top_k
        results.sort(key=lambda x: x.score or 0, reverse=True)
        return results[:top_k]
    
    def delete(
        self,
        ids: Optional[List[str]] = None,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
        delete_all: bool = False
    ) -> int:
        """Delete vectors from the store."""
        ns = namespace or self.default_namespace
        
        if delete_all:
            if ns in self._data:
                count = len(self._data[ns])
                self._data[ns] = {}
                return count
            return 0
        
        if ns not in self._data:
            return 0
        
        ns_data = self._data[ns]
        deleted = 0
        
        if ids:
            for id_ in ids:
                if id_ in ns_data:
                    del ns_data[id_]
                    deleted += 1
        elif filter:
            to_delete = []
            for id_, record in ns_data.items():
                match = True
                for key, value in filter.items():
                    if record.metadata.get(key) != value:
                        match = False
                        break
                if match:
                    to_delete.append(id_)
            for id_ in to_delete:
                del ns_data[id_]
                deleted += 1
        
        return deleted
    
    def count(self, namespace: Optional[str] = None) -> int:
        """Get the number of vectors in the store."""
        ns = namespace or self.default_namespace
        if ns in self._data:
            return len(self._data[ns])
        return 0
    
    def get(
        self,
        ids: List[str],
        namespace: Optional[str] = None
    ) -> List[VectorRecord]:
        """Get vectors by ID."""
        ns_data = self._get_namespace_data(namespace)
        results = []
        for id_ in ids:
            if id_ in ns_data:
                results.append(ns_data[id_])
        return results
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)


# Register the in-memory store by default
def _register_default_stores():
    """Register default vector stores."""
    registry = get_vector_store_registry()
    registry.register("memory", InMemoryVectorStore)


_register_default_stores()
