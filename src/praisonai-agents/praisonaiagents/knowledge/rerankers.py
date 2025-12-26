"""
Reranker Protocol for PraisonAI Agents.

This module defines the protocol for rerankers and a registry system.
NO heavy imports - only stdlib and typing.

Implementations are provided by praisonai-tools or wrapper layer.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
import logging

logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """
    Result from a reranking operation.
    
    Attributes:
        text: The text content
        score: Reranking score (higher is more relevant)
        original_index: Original position before reranking
        metadata: Optional metadata
    """
    text: str
    score: float
    original_index: int
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@runtime_checkable
class RerankerProtocol(Protocol):
    """
    Protocol for rerankers.
    
    Implementations must provide a rerank method that takes a query
    and a list of documents and returns reranked results.
    """
    
    name: str
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[RerankResult]:
        """
        Rerank documents based on relevance to query.
        
        Args:
            query: The search query
            documents: List of document texts to rerank
            top_k: Optional limit on results (None = return all)
            **kwargs: Additional reranker-specific options
            
        Returns:
            List of RerankResult objects sorted by relevance
        """
        ...
    
    async def arerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[RerankResult]:
        """Async version of rerank."""
        ...


class RerankerRegistry:
    """
    Registry for rerankers.
    """
    
    _instance: Optional["RerankerRegistry"] = None
    
    def __new__(cls) -> "RerankerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._rerankers: Dict[str, Callable[..., RerankerProtocol]] = {}
        return cls._instance
    
    def register(
        self, 
        name: str, 
        factory: Callable[..., RerankerProtocol]
    ) -> None:
        """Register a reranker factory."""
        self._rerankers[name] = factory
    
    def get(
        self, 
        name: str, 
        **kwargs
    ) -> Optional[RerankerProtocol]:
        """Get a reranker by name."""
        if name in self._rerankers:
            try:
                return self._rerankers[name](**kwargs)
            except Exception as e:
                logger.warning(f"Failed to initialize reranker '{name}': {e}")
                return None
        return None
    
    def list_rerankers(self) -> List[str]:
        """List all registered reranker names."""
        return list(self._rerankers.keys())
    
    def clear(self) -> None:
        """Clear all registered rerankers."""
        self._rerankers.clear()


def get_reranker_registry() -> RerankerRegistry:
    """Get the global reranker registry instance."""
    return RerankerRegistry()


class SimpleReranker:
    """
    Simple keyword-based reranker for testing and fallback.
    
    Uses term frequency overlap for scoring. No external dependencies.
    """
    
    name: str = "simple"
    
    def __init__(self, **kwargs):
        pass
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[RerankResult]:
        """Rerank using simple term overlap."""
        query_terms = set(query.lower().split())
        
        results = []
        for i, doc in enumerate(documents):
            doc_terms = set(doc.lower().split())
            
            # Calculate Jaccard similarity
            if not query_terms or not doc_terms:
                score = 0.0
            else:
                intersection = len(query_terms & doc_terms)
                union = len(query_terms | doc_terms)
                score = intersection / union if union > 0 else 0.0
            
            results.append(RerankResult(
                text=doc,
                score=score,
                original_index=i
            ))
        
        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        
        if top_k is not None:
            results = results[:top_k]
        
        return results
    
    async def arerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
        **kwargs
    ) -> List[RerankResult]:
        """Async version (just calls sync)."""
        return self.rerank(query, documents, top_k, **kwargs)


# Register the simple reranker by default
def _register_default_rerankers():
    """Register default rerankers."""
    registry = get_reranker_registry()
    registry.register("simple", SimpleReranker)


_register_default_rerankers()
