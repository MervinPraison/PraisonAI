"""
Index Type Selection for PraisonAI Agents.

This module defines index types and protocols.
NO heavy imports - only stdlib and typing.

Implementations are provided by the wrapper layer.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
from enum import Enum
import logging
import math

logger = logging.getLogger(__name__)


class IndexType(str, Enum):
    """Available index types."""
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    GRAPH = "graph"


@dataclass
class IndexStats:
    """Statistics about an index."""
    index_type: IndexType
    document_count: int
    chunk_count: int
    total_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IndexProtocol(Protocol):
    """
    Protocol for document indices.
    
    Implementations must provide methods for indexing and querying.
    """
    
    name: str
    index_type: IndexType
    
    def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None
    ) -> List[str]:
        """
        Add documents to the index.
        
        Args:
            texts: List of text content
            metadatas: Optional list of metadata dicts
            ids: Optional list of IDs
            embeddings: Optional pre-computed embeddings (for vector index)
            
        Returns:
            List of document IDs
        """
        ...
    
    def query(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        query_embedding: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query the index.
        
        Args:
            query: Search query
            top_k: Number of results
            filter: Optional metadata filter
            query_embedding: Optional pre-computed query embedding
            
        Returns:
            List of results with text, score, metadata
        """
        ...
    
    def delete(
        self,
        ids: Optional[List[str]] = None,
        filter: Optional[Dict[str, Any]] = None,
        delete_all: bool = False
    ) -> int:
        """Delete documents from the index."""
        ...
    
    def stats(self) -> IndexStats:
        """Get index statistics."""
        ...


class IndexRegistry:
    """Registry for index types."""
    
    _instance: Optional["IndexRegistry"] = None
    
    def __new__(cls) -> "IndexRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._indices: Dict[str, Callable[..., IndexProtocol]] = {}
        return cls._instance
    
    def register(self, name: str, factory: Callable[..., IndexProtocol]) -> None:
        """Register an index factory."""
        self._indices[name] = factory
    
    def get(self, name: str, **kwargs) -> Optional[IndexProtocol]:
        """Get an index by name."""
        if name in self._indices:
            try:
                return self._indices[name](**kwargs)
            except Exception as e:
                logger.warning(f"Failed to initialize index '{name}': {e}")
                return None
        return None
    
    def list_indices(self) -> List[str]:
        """List all registered index names."""
        return list(self._indices.keys())
    
    def clear(self) -> None:
        """Clear all registered indices."""
        self._indices.clear()


def get_index_registry() -> IndexRegistry:
    """Get the global index registry instance."""
    return IndexRegistry()


class KeywordIndex:
    """
    Simple BM25-like keyword index.
    
    Pure Python implementation with no external dependencies.
    """
    
    name: str = "keyword"
    index_type: IndexType = IndexType.KEYWORD
    
    def __init__(self, k1: float = 1.5, b: float = 0.75, **kwargs):
        self.k1 = k1
        self.b = b
        self._documents: Dict[str, Dict[str, Any]] = {}  # id -> {text, metadata, terms}
        self._term_doc_freq: Dict[str, int] = {}  # term -> doc count
        self._avg_doc_len: float = 0.0
        self._total_docs: int = 0
    
    def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None
    ) -> List[str]:
        """Add documents to the keyword index."""
        import uuid
        
        metadatas = metadatas or [{} for _ in texts]
        ids = ids or [str(uuid.uuid4()) for _ in texts]
        
        total_len = sum(len(doc["text"].split()) for doc in self._documents.values())
        
        for text, metadata, doc_id in zip(texts, metadatas, ids):
            terms = self._tokenize(text)
            term_freq = {}
            for term in terms:
                term_freq[term] = term_freq.get(term, 0) + 1
            
            self._documents[doc_id] = {
                "text": text,
                "metadata": metadata,
                "terms": term_freq,
                "length": len(terms)
            }
            
            # Update document frequency
            for term in set(terms):
                self._term_doc_freq[term] = self._term_doc_freq.get(term, 0) + 1
            
            total_len += len(terms)
        
        self._total_docs = len(self._documents)
        self._avg_doc_len = total_len / self._total_docs if self._total_docs > 0 else 0
        
        return ids
    
    def query(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        query_embedding: Optional[List[float]] = None
    ) -> List[Dict[str, Any]]:
        """Query using BM25 scoring."""
        query_terms = self._tokenize(query)
        
        scores = []
        for doc_id, doc in self._documents.items():
            # Apply filter
            if filter:
                match = True
                for key, value in filter.items():
                    if doc["metadata"].get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            score = self._bm25_score(query_terms, doc)
            scores.append({
                "id": doc_id,
                "text": doc["text"],
                "score": score,
                "metadata": doc["metadata"]
            })
        
        # Sort by score
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]
    
    def delete(
        self,
        ids: Optional[List[str]] = None,
        filter: Optional[Dict[str, Any]] = None,
        delete_all: bool = False
    ) -> int:
        """Delete documents from the index."""
        if delete_all:
            count = len(self._documents)
            self._documents.clear()
            self._term_doc_freq.clear()
            self._total_docs = 0
            self._avg_doc_len = 0
            return count
        
        deleted = 0
        to_delete = []
        
        if ids:
            to_delete = [id_ for id_ in ids if id_ in self._documents]
        elif filter:
            for doc_id, doc in self._documents.items():
                match = True
                for key, value in filter.items():
                    if doc["metadata"].get(key) != value:
                        match = False
                        break
                if match:
                    to_delete.append(doc_id)
        
        for doc_id in to_delete:
            doc = self._documents[doc_id]
            # Update term frequencies
            for term in doc["terms"]:
                if term in self._term_doc_freq:
                    self._term_doc_freq[term] -= 1
                    if self._term_doc_freq[term] <= 0:
                        del self._term_doc_freq[term]
            del self._documents[doc_id]
            deleted += 1
        
        self._total_docs = len(self._documents)
        if self._total_docs > 0:
            self._avg_doc_len = sum(d["length"] for d in self._documents.values()) / self._total_docs
        else:
            self._avg_doc_len = 0
        
        return deleted
    
    def stats(self) -> IndexStats:
        """Get index statistics."""
        return IndexStats(
            index_type=self.index_type,
            document_count=self._total_docs,
            chunk_count=self._total_docs,
            total_tokens=sum(d["length"] for d in self._documents.values()),
            metadata={"unique_terms": len(self._term_doc_freq)}
        )
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        import re
        # Lowercase and split on non-alphanumeric
        tokens = re.findall(r'\b\w+\b', text.lower())
        # Remove very short tokens
        return [t for t in tokens if len(t) > 1]
    
    def _bm25_score(self, query_terms: List[str], doc: Dict[str, Any]) -> float:
        """Calculate BM25 score."""
        score = 0.0
        doc_len = doc["length"]
        term_freq = doc["terms"]
        
        for term in query_terms:
            if term not in term_freq:
                continue
            
            tf = term_freq[term]
            df = self._term_doc_freq.get(term, 0)
            
            # IDF component
            idf = math.log((self._total_docs - df + 0.5) / (df + 0.5) + 1)
            
            # TF component with length normalization
            tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self._avg_doc_len))
            
            score += idf * tf_norm
        
        return score


# Register the keyword index by default
def _register_default_indices():
    """Register default indices."""
    registry = get_index_registry()
    registry.register("keyword", KeywordIndex)


_register_default_indices()
