"""
Vector Stores Capabilities Module

Provides vector store management functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict


@dataclass
class VectorStoreResult:
    """Result from vector store operations."""
    id: str
    object: str = "vector_store"
    name: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[int] = None
    file_counts: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorSearchResult:
    """Result from vector store search."""
    results: List[Dict[str, Any]]
    query: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def vector_store_create(
    name: str,
    file_ids: Optional[List[str]] = None,
    expires_after: Optional[Dict[str, Any]] = None,
    chunking_strategy: Optional[Dict[str, Any]] = None,
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    store_metadata: Optional[Dict[str, str]] = None,
    **kwargs
) -> VectorStoreResult:
    """
    Create a vector store.
    
    Args:
        name: Name of the vector store
        file_ids: List of file IDs to add to the store
        expires_after: Expiration policy
        chunking_strategy: Chunking configuration
        custom_llm_provider: Provider ("openai")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        store_metadata: Optional metadata for the store
        
    Returns:
        VectorStoreResult with store ID
        
    Example:
        >>> result = vector_store_create("my-store", file_ids=["file-abc123"])
        >>> print(result.id)
    """
    import litellm
    
    call_kwargs = {
        'name': name,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if file_ids:
        call_kwargs['file_ids'] = file_ids
    if expires_after:
        call_kwargs['expires_after'] = expires_after
    if chunking_strategy:
        call_kwargs['chunking_strategy'] = chunking_strategy
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    if store_metadata:
        call_kwargs['metadata'] = store_metadata
    
    call_kwargs.update(kwargs)
    
    response = litellm.create_vector_store(**call_kwargs)
    
    file_counts = None
    if hasattr(response, 'file_counts'):
        file_counts = {
            'in_progress': getattr(response.file_counts, 'in_progress', 0),
            'completed': getattr(response.file_counts, 'completed', 0),
            'failed': getattr(response.file_counts, 'failed', 0),
            'cancelled': getattr(response.file_counts, 'cancelled', 0),
            'total': getattr(response.file_counts, 'total', 0),
        }
    
    return VectorStoreResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'vector_store'),
        name=getattr(response, 'name', name),
        status=getattr(response, 'status', None),
        created_at=getattr(response, 'created_at', None),
        file_counts=file_counts,
        metadata=store_metadata or {},
    )


async def avector_store_create(
    name: str,
    file_ids: Optional[List[str]] = None,
    expires_after: Optional[Dict[str, Any]] = None,
    chunking_strategy: Optional[Dict[str, Any]] = None,
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    store_metadata: Optional[Dict[str, str]] = None,
    **kwargs
) -> VectorStoreResult:
    """
    Async: Create a vector store.
    
    See vector_store_create() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'name': name,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if file_ids:
        call_kwargs['file_ids'] = file_ids
    if expires_after:
        call_kwargs['expires_after'] = expires_after
    if chunking_strategy:
        call_kwargs['chunking_strategy'] = chunking_strategy
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    if store_metadata:
        call_kwargs['metadata'] = store_metadata
    
    call_kwargs.update(kwargs)
    
    response = await litellm.acreate_vector_store(**call_kwargs)
    
    file_counts = None
    if hasattr(response, 'file_counts'):
        file_counts = {
            'in_progress': getattr(response.file_counts, 'in_progress', 0),
            'completed': getattr(response.file_counts, 'completed', 0),
            'failed': getattr(response.file_counts, 'failed', 0),
            'cancelled': getattr(response.file_counts, 'cancelled', 0),
            'total': getattr(response.file_counts, 'total', 0),
        }
    
    return VectorStoreResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'vector_store'),
        name=getattr(response, 'name', name),
        status=getattr(response, 'status', None),
        created_at=getattr(response, 'created_at', None),
        file_counts=file_counts,
        metadata=store_metadata or {},
    )


def vector_store_search(
    vector_store_id: str,
    query: str,
    max_num_results: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> VectorSearchResult:
    """
    Search a vector store.
    
    Args:
        vector_store_id: ID of the vector store
        query: Search query
        max_num_results: Maximum number of results
        filters: Optional filters
        custom_llm_provider: Provider
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        VectorSearchResult with search results
        
    Example:
        >>> result = vector_store_search("vs-abc123", "What is AI?")
        >>> for r in result.results:
        ...     print(r['score'], r['content'])
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
        'query': query,
        'max_num_results': max_num_results,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if filters:
        call_kwargs['filters'] = filters
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.search_vector_store(**call_kwargs)
    
    results = []
    if hasattr(response, 'data'):
        for item in response.data:
            result_dict = {
                'score': getattr(item, 'score', 0.0),
            }
            if hasattr(item, 'content'):
                content_list = []
                for c in item.content:
                    content_list.append({
                        'type': getattr(c, 'type', 'text'),
                        'text': getattr(c, 'text', ''),
                    })
                result_dict['content'] = content_list
            results.append(result_dict)
    
    return VectorSearchResult(
        results=results,
        query=query,
    )


async def avector_store_search(
    vector_store_id: str,
    query: str,
    max_num_results: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> VectorSearchResult:
    """
    Async: Search a vector store.
    
    See vector_store_search() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
        'query': query,
        'max_num_results': max_num_results,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if filters:
        call_kwargs['filters'] = filters
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.asearch_vector_store(**call_kwargs)
    
    results = []
    if hasattr(response, 'data'):
        for item in response.data:
            result_dict = {
                'score': getattr(item, 'score', 0.0),
            }
            if hasattr(item, 'content'):
                content_list = []
                for c in item.content:
                    content_list.append({
                        'type': getattr(c, 'type', 'text'),
                        'text': getattr(c, 'text', ''),
                    })
                result_dict['content'] = content_list
            results.append(result_dict)
    
    return VectorSearchResult(
        results=results,
        query=query,
    )
