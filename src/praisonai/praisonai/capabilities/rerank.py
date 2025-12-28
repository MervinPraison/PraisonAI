"""
Rerank Capabilities Module

Provides document reranking functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict


@dataclass
class RerankResult:
    """Result from document reranking."""
    results: List[Dict[str, Any]]
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def rerank(
    query: str,
    documents: List[Union[str, Dict[str, Any]]],
    model: str = "cohere/rerank-english-v3.0",
    top_n: Optional[int] = None,
    rank_fields: Optional[List[str]] = None,
    return_documents: bool = True,
    max_chunks_per_doc: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> RerankResult:
    """
    Rerank documents based on relevance to a query.
    
    Args:
        query: The query to rank documents against
        documents: List of documents (strings or dicts with text field)
        model: Model name (e.g., "cohere/rerank-english-v3.0")
        top_n: Number of top results to return
        rank_fields: Fields to use for ranking (for dict documents)
        return_documents: Whether to return document content
        max_chunks_per_doc: Maximum chunks per document
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        RerankResult with ranked documents
        
    Example:
        >>> result = rerank("What is AI?", ["AI is...", "Machine learning..."])
        >>> for r in result.results:
        ...     print(r['index'], r['relevance_score'])
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'query': query,
        'documents': documents,
        'return_documents': return_documents,
        'timeout': timeout,
    }
    
    if top_n:
        call_kwargs['top_n'] = top_n
    if rank_fields:
        call_kwargs['rank_fields'] = rank_fields
    if max_chunks_per_doc:
        call_kwargs['max_chunks_per_doc'] = max_chunks_per_doc
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.rerank(**call_kwargs)
    
    results = []
    if hasattr(response, 'results'):
        for item in response.results:
            result_dict = {
                'index': getattr(item, 'index', 0),
                'relevance_score': getattr(item, 'relevance_score', 0.0),
            }
            if return_documents and hasattr(item, 'document'):
                result_dict['document'] = item.document
            results.append(result_dict)
    
    return RerankResult(
        results=results,
        model=model,
        metadata=metadata or {},
    )


async def arerank(
    query: str,
    documents: List[Union[str, Dict[str, Any]]],
    model: str = "cohere/rerank-english-v3.0",
    top_n: Optional[int] = None,
    rank_fields: Optional[List[str]] = None,
    return_documents: bool = True,
    max_chunks_per_doc: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> RerankResult:
    """
    Async: Rerank documents based on relevance to a query.
    
    See rerank() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'query': query,
        'documents': documents,
        'return_documents': return_documents,
        'timeout': timeout,
    }
    
    if top_n:
        call_kwargs['top_n'] = top_n
    if rank_fields:
        call_kwargs['rank_fields'] = rank_fields
    if max_chunks_per_doc:
        call_kwargs['max_chunks_per_doc'] = max_chunks_per_doc
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.arerank(**call_kwargs)
    
    results = []
    if hasattr(response, 'results'):
        for item in response.results:
            result_dict = {
                'index': getattr(item, 'index', 0),
                'relevance_score': getattr(item, 'relevance_score', 0.0),
            }
            if return_documents and hasattr(item, 'document'):
                result_dict['document'] = item.document
            results.append(result_dict)
    
    return RerankResult(
        results=results,
        model=model,
        metadata=metadata or {},
    )
