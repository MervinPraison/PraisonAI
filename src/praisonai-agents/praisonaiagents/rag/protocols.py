"""
RAG Protocols for PraisonAI Agents.

Defines minimal protocol interfaces for RAG components.
No heavy imports - only stdlib and typing.
"""

from typing import Any, Dict, Iterator, List, Optional, Protocol, runtime_checkable

from .models import Citation, RAGResult


@runtime_checkable
class ContextBuilderProtocol(Protocol):
    """
    Protocol for building context from retrieval results.
    
    Implementations must provide a build method that assembles
    context from search results with token-aware truncation.
    """
    
    def build(
        self,
        results: List[Dict[str, Any]],
        max_tokens: int = 4000,
        deduplicate: bool = True,
    ) -> str:
        """
        Build context string from retrieval results.
        
        Args:
            results: List of search results with 'text' and 'metadata' keys
            max_tokens: Maximum tokens for context
            deduplicate: Whether to deduplicate similar chunks
            
        Returns:
            Assembled context string
        """
        ...


@runtime_checkable
class CitationFormatterProtocol(Protocol):
    """
    Protocol for formatting citations from retrieval results.
    
    Implementations must provide a format method that creates
    Citation objects from search results.
    """
    
    def format(
        self,
        results: List[Dict[str, Any]],
        start_id: int = 1,
    ) -> List[Citation]:
        """
        Format retrieval results as citations.
        
        Args:
            results: List of search results
            start_id: Starting citation ID number
            
        Returns:
            List of Citation objects
        """
        ...


@runtime_checkable
class RerankerProtocol(Protocol):
    """
    Protocol for reranking retrieval results.
    
    Implementations must provide a rerank method that reorders
    results by relevance to the query.
    """
    
    name: str
    
    def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank results by relevance to query.
        
        Args:
            query: The search query
            results: List of results to rerank
            top_k: Optional limit on results
            
        Returns:
            Reranked list of results
        """
        ...


@runtime_checkable
class RAGProtocol(Protocol):
    """
    Protocol for RAG pipelines.
    
    Implementations must provide query, stream, and async variants.
    """
    
    def query(self, question: str, **kwargs) -> RAGResult:
        """Execute RAG query and return result with citations."""
        ...
    
    async def aquery(self, question: str, **kwargs) -> RAGResult:
        """Async version of query."""
        ...
    
    def stream(self, question: str, **kwargs) -> Iterator[str]:
        """Stream RAG response tokens."""
        ...


@runtime_checkable
class RetrievalStrategyProtocol(Protocol):
    """
    Protocol for pluggable retrieval strategies.
    
    Enables custom retrieval algorithms without modifying core RAG pipeline.
    Implementations can provide different retrieval approaches (semantic,
    keyword, hybrid, graph-based, etc.) through a unified interface.
    """
    
    name: str
    
    def retrieve(
        self,
        query: str,
        knowledge_store: Any,  # KnowledgeStoreProtocol
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents for query.
        
        Args:
            query: Search query string
            knowledge_store: Knowledge store to search
            limit: Maximum number of results
            filters: Optional metadata filters
            **kwargs: Strategy-specific options
            
        Returns:
            List of retrieved documents with metadata
        """
        ...
    
    async def aretrieve(
        self,
        query: str,
        knowledge_store: Any,  # KnowledgeStoreProtocol
        *,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Async version of retrieve.
        
        Args:
            query: Search query string
            knowledge_store: Knowledge store to search
            limit: Maximum number of results
            filters: Optional metadata filters
            **kwargs: Strategy-specific options
            
        Returns:
            List of retrieved documents with metadata
        """
        ...


@runtime_checkable
class GraphHookProtocol(Protocol):
    """
    Protocol for graph-based retrieval hooks (optional).
    
    Implementations can provide graph traversal for enhanced retrieval.
    This is an optional extension point for GraphRAG tools.
    """
    
    def get_related_nodes(
        self,
        query: str,
        node_ids: List[str],
        max_hops: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Get related nodes from graph for context expansion.
        
        Args:
            query: The search query
            node_ids: Starting node IDs
            max_hops: Maximum graph traversal hops
            
        Returns:
            List of related nodes with metadata
        """
        ...
