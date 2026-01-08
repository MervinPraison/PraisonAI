"""
Smart Retriever for PraisonAI Agents (Phase 4).

Provides enhanced retrieval with:
- Hybrid retrieval (keyword + semantic)
- Metadata filtering
- Path/glob filtering
- Pluggable reranking

No heavy imports at module level.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class RetrieverProtocol(Protocol):
    """Protocol for retrieval implementations."""
    
    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks for query."""
        ...


@runtime_checkable
class RerankerProtocol(Protocol):
    """Protocol for reranking implementations."""
    
    name: str
    
    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Rerank results by relevance to query."""
        ...


@dataclass
class RetrievalResult:
    """Result of a retrieval operation."""
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    total_found: int = 0
    strategy_used: str = "basic"
    reranked: bool = False
    filtered: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class SmartRetriever:
    """
    Enhanced retriever with hybrid search, filtering, and reranking.
    
    Implements the retrieval ladder based on strategy:
    - DIRECT: Return all content
    - BASIC: Semantic search only
    - HYBRID: Keyword + semantic search
    - RERANKED: Hybrid + cross-encoder reranking
    """
    
    def __init__(
        self,
        knowledge=None,
        reranker: Optional[RerankerProtocol] = None,
        verbose: bool = False,
    ):
        """
        Initialize SmartRetriever.
        
        Args:
            knowledge: Knowledge instance for retrieval
            reranker: Optional reranker implementation
            verbose: Enable verbose logging
        """
        self._knowledge = knowledge
        self._reranker = reranker
        self._verbose = verbose
    
    def retrieve(
        self,
        query: str,
        strategy: str = "basic",
        top_k: int = 10,
        rerank_top_k: Optional[int] = None,
        include_glob: Optional[List[str]] = None,
        exclude_glob: Optional[List[str]] = None,
        path_filter: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> RetrievalResult:
        """
        Retrieve relevant chunks using specified strategy.
        
        Args:
            query: Search query
            strategy: Retrieval strategy (direct, basic, hybrid, reranked)
            top_k: Number of results to return
            rerank_top_k: Number of results after reranking
            include_glob: Glob patterns to include
            exclude_glob: Glob patterns to exclude
            path_filter: Regex for path filtering
            metadata_filters: Metadata key-value filters
            user_id: User ID for scoping
            agent_id: Agent ID for scoping
            
        Returns:
            RetrievalResult with chunks and metadata
        """
        result = RetrievalResult(strategy_used=strategy)
        
        if not self._knowledge:
            return result
        
        # Get initial results from knowledge store
        search_results = self._search(
            query=query,
            top_k=top_k * 3 if strategy in ("reranked", "hybrid") else top_k,
            user_id=user_id,
            agent_id=agent_id,
        )
        
        chunks = self._normalize_results(search_results)
        result.total_found = len(chunks)
        
        # Apply filters
        if include_glob or exclude_glob or path_filter or metadata_filters:
            chunks = self._apply_filters(
                chunks,
                include_glob=include_glob,
                exclude_glob=exclude_glob,
                path_filter=path_filter,
                metadata_filters=metadata_filters,
            )
            result.filtered = True
        
        # Apply reranking if strategy requires it
        if strategy in ("reranked", "compressed", "hierarchical") and self._reranker:
            chunks = self._reranker.rerank(query, chunks, top_k=rerank_top_k or top_k)
            result.reranked = True
        
        # Limit to top_k
        result.chunks = chunks[:top_k]
        
        return result
    
    def _search(
        self,
        query: str,
        top_k: int,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Any:
        """Perform search on knowledge store."""
        try:
            return self._knowledge.search(
                query,
                user_id=user_id,
                agent_id=agent_id,
                limit=top_k,
            )
        except Exception:
            return []
    
    def _normalize_results(self, results: Any) -> List[Dict[str, Any]]:
        """Normalize search results to list of dicts."""
        if not results:
            return []
        
        # Handle dict with 'results' key
        if isinstance(results, dict):
            if 'results' in results:
                items = results.get('results', [])
            else:
                items = [results]
        elif isinstance(results, list):
            items = results
        else:
            return []
        
        normalized = []
        for item in items:
            if item is None:
                continue
            if isinstance(item, dict):
                text = item.get('text') or item.get('memory', '')
                metadata = item.get('metadata') or {}
                normalized.append({
                    'text': str(text),
                    'metadata': metadata if isinstance(metadata, dict) else {},
                    'score': float(item.get('score', 0.0) or 0.0),
                })
        
        return normalized
    
    def _apply_filters(
        self,
        chunks: List[Dict[str, Any]],
        include_glob: Optional[List[str]] = None,
        exclude_glob: Optional[List[str]] = None,
        path_filter: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Apply filters to chunks."""
        import fnmatch
        import re
        
        filtered = []
        
        for chunk in chunks:
            metadata = chunk.get('metadata', {})
            filename = metadata.get('filename', '')
            filepath = metadata.get('filepath', metadata.get('source', ''))
            
            # Check include patterns
            if include_glob:
                matched = False
                for pattern in include_glob:
                    if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(filepath, pattern):
                        matched = True
                        break
                if not matched:
                    continue
            
            # Check exclude patterns
            if exclude_glob:
                excluded = False
                for pattern in exclude_glob:
                    if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(filepath, pattern):
                        excluded = True
                        break
                if excluded:
                    continue
            
            # Check path filter regex
            if path_filter:
                try:
                    if not re.search(path_filter, filepath):
                        continue
                except re.error:
                    pass
            
            # Check metadata filters
            if metadata_filters:
                match = True
                for key, value in metadata_filters.items():
                    if metadata.get(key) != value:
                        match = False
                        break
                if not match:
                    continue
            
            filtered.append(chunk)
        
        return filtered


class SimpleReranker:
    """
    Simple reranker using keyword matching.
    
    For production, use cross-encoder models like:
    - sentence-transformers/ms-marco-MiniLM-L-6-v2
    - Cohere Rerank API
    """
    
    name = "simple"
    
    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Rerank results by keyword overlap with query."""
        query_words = set(query.lower().split())
        
        scored = []
        for result in results:
            text = result.get('text', '').lower()
            text_words = set(text.split())
            
            # Calculate overlap score
            overlap = len(query_words & text_words)
            original_score = result.get('score', 0.0)
            
            # Combined score
            combined_score = original_score + (overlap * 0.1)
            
            scored.append({
                **result,
                'score': combined_score,
                '_rerank_overlap': overlap,
            })
        
        # Sort by combined score
        scored.sort(key=lambda x: x['score'], reverse=True)
        
        if top_k:
            return scored[:top_k]
        return scored
