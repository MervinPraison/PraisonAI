"""
Retrieval Strategy Patterns for PraisonAI Agents.

This module defines protocols and strategies for document retrieval.
NO heavy imports - only stdlib and typing.

Implementations are provided by the wrapper layer.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RetrievalStrategy(str, Enum):
    """Available retrieval strategies."""
    BASIC = "basic"
    FUSION = "fusion"
    RECURSIVE = "recursive"
    AUTO_MERGE = "auto_merge"
    HYBRID = "hybrid"


@dataclass
class RetrievalResult:
    """
    Result from a retrieval operation.
    
    Attributes:
        text: The retrieved text content
        score: Relevance score (0-1)
        metadata: Source metadata
        doc_id: Document identifier
        chunk_index: Index of chunk within document
    """
    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    doc_id: Optional[str] = None
    chunk_index: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index
        }


@runtime_checkable
class RetrieverProtocol(Protocol):
    """
    Protocol for document retrievers.
    
    Implementations must provide a retrieve method that takes a query
    and returns relevant documents.
    """
    
    name: str
    strategy: RetrievalStrategy
    
    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[RetrievalResult]:
        """
        Retrieve relevant documents for a query.
        
        Args:
            query: The search query
            top_k: Maximum number of results
            filter: Optional metadata filter
            **kwargs: Additional retriever-specific options
            
        Returns:
            List of RetrievalResult objects sorted by relevance
        """
        ...
    
    async def aretrieve(
        self,
        query: str,
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[RetrievalResult]:
        """Async version of retrieve."""
        ...


class RetrieverRegistry:
    """
    Registry for retrieval strategies.
    """
    
    _instance: Optional["RetrieverRegistry"] = None
    
    def __new__(cls) -> "RetrieverRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._retrievers: Dict[str, Callable[..., RetrieverProtocol]] = {}
        return cls._instance
    
    def register(
        self, 
        name: str, 
        factory: Callable[..., RetrieverProtocol]
    ) -> None:
        """Register a retriever factory."""
        self._retrievers[name] = factory
    
    def get(
        self, 
        name: str, 
        **kwargs
    ) -> Optional[RetrieverProtocol]:
        """Get a retriever by name."""
        if name in self._retrievers:
            try:
                return self._retrievers[name](**kwargs)
            except Exception as e:
                logger.warning(f"Failed to initialize retriever '{name}': {e}")
                return None
        return None
    
    def list_retrievers(self) -> List[str]:
        """List all registered retriever names."""
        return list(self._retrievers.keys())
    
    def clear(self) -> None:
        """Clear all registered retrievers."""
        self._retrievers.clear()


def get_retriever_registry() -> RetrieverRegistry:
    """Get the global retriever registry instance."""
    return RetrieverRegistry()


def reciprocal_rank_fusion(
    result_lists: List[List[RetrievalResult]],
    k: int = 60
) -> List[RetrievalResult]:
    """
    Reciprocal Rank Fusion (RRF) algorithm for combining multiple result lists.
    
    Pure Python implementation with no external dependencies.
    
    Args:
        result_lists: List of result lists from different retrievers
        k: RRF constant (default 60)
        
    Returns:
        Fused and re-ranked list of results
    """
    # Track scores by document ID
    fused_scores: Dict[str, float] = {}
    doc_map: Dict[str, RetrievalResult] = {}
    
    for results in result_lists:
        for rank, result in enumerate(results):
            doc_key = result.doc_id or result.text[:100]  # Use text prefix as fallback key
            
            # RRF score: 1 / (k + rank)
            rrf_score = 1.0 / (k + rank + 1)
            
            if doc_key in fused_scores:
                fused_scores[doc_key] += rrf_score
            else:
                fused_scores[doc_key] = rrf_score
                doc_map[doc_key] = result
    
    # Sort by fused score
    sorted_keys = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)
    
    # Build result list with updated scores
    fused_results = []
    for key in sorted_keys:
        result = doc_map[key]
        fused_results.append(RetrievalResult(
            text=result.text,
            score=fused_scores[key],
            metadata=result.metadata,
            doc_id=result.doc_id,
            chunk_index=result.chunk_index
        ))
    
    return fused_results


def merge_adjacent_chunks(
    results: List[RetrievalResult],
    max_gap: int = 1
) -> List[RetrievalResult]:
    """
    Merge adjacent chunks from the same document.
    
    Args:
        results: List of retrieval results
        max_gap: Maximum gap between chunk indices to merge
        
    Returns:
        Merged results
    """
    if not results:
        return results
    
    # Group by document ID
    doc_groups: Dict[str, List[RetrievalResult]] = {}
    for result in results:
        doc_id = result.doc_id or "unknown"
        if doc_id not in doc_groups:
            doc_groups[doc_id] = []
        doc_groups[doc_id].append(result)
    
    merged_results = []
    
    for doc_id, chunks in doc_groups.items():
        # Sort by chunk index
        chunks_with_index = [c for c in chunks if c.chunk_index is not None]
        chunks_without_index = [c for c in chunks if c.chunk_index is None]
        
        if not chunks_with_index:
            merged_results.extend(chunks_without_index)
            continue
        
        chunks_with_index.sort(key=lambda x: x.chunk_index or 0)
        
        # Merge adjacent chunks
        current_group = [chunks_with_index[0]]
        
        for chunk in chunks_with_index[1:]:
            last_chunk = current_group[-1]
            last_idx = last_chunk.chunk_index or 0
            curr_idx = chunk.chunk_index or 0
            
            if curr_idx - last_idx <= max_gap:
                current_group.append(chunk)
            else:
                # Merge current group and start new one
                merged_results.append(_merge_chunk_group(current_group))
                current_group = [chunk]
        
        # Don't forget the last group
        if current_group:
            merged_results.append(_merge_chunk_group(current_group))
        
        merged_results.extend(chunks_without_index)
    
    # Sort by score
    merged_results.sort(key=lambda x: x.score, reverse=True)
    return merged_results


def _merge_chunk_group(chunks: List[RetrievalResult]) -> RetrievalResult:
    """Merge a group of chunks into a single result."""
    if len(chunks) == 1:
        return chunks[0]
    
    # Combine text
    merged_text = "\n".join(c.text for c in chunks)
    
    # Average score
    avg_score = sum(c.score for c in chunks) / len(chunks)
    
    # Use first chunk's metadata
    metadata = chunks[0].metadata.copy()
    metadata["merged_chunks"] = len(chunks)
    
    return RetrievalResult(
        text=merged_text,
        score=avg_score,
        metadata=metadata,
        doc_id=chunks[0].doc_id,
        chunk_index=chunks[0].chunk_index
    )
