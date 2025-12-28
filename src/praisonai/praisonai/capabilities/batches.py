"""
Batches Capabilities Module

Provides batch processing functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict, Literal


@dataclass
class BatchResult:
    """Result from batch operations."""
    id: str
    object: str = "batch"
    endpoint: Optional[str] = None
    status: Optional[str] = None
    input_file_id: Optional[str] = None
    output_file_id: Optional[str] = None
    error_file_id: Optional[str] = None
    created_at: Optional[int] = None
    completed_at: Optional[int] = None
    request_counts: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def batch_create(
    input_file_id: str,
    endpoint: Literal["/v1/chat/completions", "/v1/embeddings"] = "/v1/chat/completions",
    completion_window: str = "24h",
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    batch_metadata: Optional[Dict[str, str]] = None,
    **kwargs
) -> BatchResult:
    """
    Create a batch processing job.
    
    Args:
        input_file_id: ID of the input file (from file_create with purpose="batch")
        endpoint: The endpoint to use ("/v1/chat/completions" or "/v1/embeddings")
        completion_window: Time window for completion ("24h")
        custom_llm_provider: Provider ("openai", "azure")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        batch_metadata: Optional metadata for the batch
        
    Returns:
        BatchResult with batch ID and status
        
    Example:
        >>> result = batch_create("file-abc123")
        >>> print(result.id, result.status)
    """
    import litellm
    
    call_kwargs = {
        'input_file_id': input_file_id,
        'endpoint': endpoint,
        'completion_window': completion_window,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    if batch_metadata:
        call_kwargs['metadata'] = batch_metadata
    
    call_kwargs.update(kwargs)
    
    response = litellm.create_batch(**call_kwargs)
    
    request_counts = None
    if hasattr(response, 'request_counts'):
        request_counts = {
            'total': getattr(response.request_counts, 'total', 0),
            'completed': getattr(response.request_counts, 'completed', 0),
            'failed': getattr(response.request_counts, 'failed', 0),
        }
    
    return BatchResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'batch'),
        endpoint=getattr(response, 'endpoint', endpoint),
        status=getattr(response, 'status', None),
        input_file_id=getattr(response, 'input_file_id', input_file_id),
        output_file_id=getattr(response, 'output_file_id', None),
        error_file_id=getattr(response, 'error_file_id', None),
        created_at=getattr(response, 'created_at', None),
        completed_at=getattr(response, 'completed_at', None),
        request_counts=request_counts,
        metadata=batch_metadata or {},
    )


async def abatch_create(
    input_file_id: str,
    endpoint: Literal["/v1/chat/completions", "/v1/embeddings"] = "/v1/chat/completions",
    completion_window: str = "24h",
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    batch_metadata: Optional[Dict[str, str]] = None,
    **kwargs
) -> BatchResult:
    """
    Async: Create a batch processing job.
    
    See batch_create() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'input_file_id': input_file_id,
        'endpoint': endpoint,
        'completion_window': completion_window,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    if batch_metadata:
        call_kwargs['metadata'] = batch_metadata
    
    call_kwargs.update(kwargs)
    
    response = await litellm.acreate_batch(**call_kwargs)
    
    request_counts = None
    if hasattr(response, 'request_counts'):
        request_counts = {
            'total': getattr(response.request_counts, 'total', 0),
            'completed': getattr(response.request_counts, 'completed', 0),
            'failed': getattr(response.request_counts, 'failed', 0),
        }
    
    return BatchResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'batch'),
        endpoint=getattr(response, 'endpoint', endpoint),
        status=getattr(response, 'status', None),
        input_file_id=getattr(response, 'input_file_id', input_file_id),
        output_file_id=getattr(response, 'output_file_id', None),
        error_file_id=getattr(response, 'error_file_id', None),
        created_at=getattr(response, 'created_at', None),
        completed_at=getattr(response, 'completed_at', None),
        request_counts=request_counts,
        metadata=batch_metadata or {},
    )


def batch_retrieve(
    batch_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> BatchResult:
    """
    Retrieve a batch by ID.
    
    Args:
        batch_id: The batch ID
        custom_llm_provider: Provider
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        BatchResult with batch status
    """
    import litellm
    
    call_kwargs = {
        'batch_id': batch_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.retrieve_batch(**call_kwargs)
    
    request_counts = None
    if hasattr(response, 'request_counts'):
        request_counts = {
            'total': getattr(response.request_counts, 'total', 0),
            'completed': getattr(response.request_counts, 'completed', 0),
            'failed': getattr(response.request_counts, 'failed', 0),
        }
    
    return BatchResult(
        id=getattr(response, 'id', batch_id),
        object=getattr(response, 'object', 'batch'),
        endpoint=getattr(response, 'endpoint', None),
        status=getattr(response, 'status', None),
        input_file_id=getattr(response, 'input_file_id', None),
        output_file_id=getattr(response, 'output_file_id', None),
        error_file_id=getattr(response, 'error_file_id', None),
        created_at=getattr(response, 'created_at', None),
        completed_at=getattr(response, 'completed_at', None),
        request_counts=request_counts,
    )


async def abatch_retrieve(
    batch_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> BatchResult:
    """
    Async: Retrieve a batch by ID.
    
    See batch_retrieve() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'batch_id': batch_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.aretrieve_batch(**call_kwargs)
    
    request_counts = None
    if hasattr(response, 'request_counts'):
        request_counts = {
            'total': getattr(response.request_counts, 'total', 0),
            'completed': getattr(response.request_counts, 'completed', 0),
            'failed': getattr(response.request_counts, 'failed', 0),
        }
    
    return BatchResult(
        id=getattr(response, 'id', batch_id),
        object=getattr(response, 'object', 'batch'),
        endpoint=getattr(response, 'endpoint', None),
        status=getattr(response, 'status', None),
        input_file_id=getattr(response, 'input_file_id', None),
        output_file_id=getattr(response, 'output_file_id', None),
        error_file_id=getattr(response, 'error_file_id', None),
        created_at=getattr(response, 'created_at', None),
        completed_at=getattr(response, 'completed_at', None),
        request_counts=request_counts,
    )


def batch_list(
    custom_llm_provider: str = "openai",
    after: Optional[str] = None,
    limit: int = 20,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[BatchResult]:
    """
    List batches.
    
    Args:
        custom_llm_provider: Provider
        after: Cursor for pagination
        limit: Maximum number of batches to return
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        List of BatchResult objects
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
        'limit': limit,
    }
    
    if after:
        call_kwargs['after'] = after
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.list_batches(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            request_counts = None
            if hasattr(item, 'request_counts'):
                request_counts = {
                    'total': getattr(item.request_counts, 'total', 0),
                    'completed': getattr(item.request_counts, 'completed', 0),
                    'failed': getattr(item.request_counts, 'failed', 0),
                }
            
            results.append(BatchResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'batch'),
                endpoint=getattr(item, 'endpoint', None),
                status=getattr(item, 'status', None),
                input_file_id=getattr(item, 'input_file_id', None),
                output_file_id=getattr(item, 'output_file_id', None),
                error_file_id=getattr(item, 'error_file_id', None),
                created_at=getattr(item, 'created_at', None),
                completed_at=getattr(item, 'completed_at', None),
                request_counts=request_counts,
            ))
    
    return results


async def abatch_list(
    custom_llm_provider: str = "openai",
    after: Optional[str] = None,
    limit: int = 20,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[BatchResult]:
    """
    Async: List batches.
    
    See batch_list() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
        'limit': limit,
    }
    
    if after:
        call_kwargs['after'] = after
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.alist_batches(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            request_counts = None
            if hasattr(item, 'request_counts'):
                request_counts = {
                    'total': getattr(item.request_counts, 'total', 0),
                    'completed': getattr(item.request_counts, 'completed', 0),
                    'failed': getattr(item.request_counts, 'failed', 0),
                }
            
            results.append(BatchResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'batch'),
                endpoint=getattr(item, 'endpoint', None),
                status=getattr(item, 'status', None),
                input_file_id=getattr(item, 'input_file_id', None),
                output_file_id=getattr(item, 'output_file_id', None),
                error_file_id=getattr(item, 'error_file_id', None),
                created_at=getattr(item, 'created_at', None),
                completed_at=getattr(item, 'completed_at', None),
                request_counts=request_counts,
            ))
    
    return results


def batch_cancel(
    batch_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> BatchResult:
    """
    Cancel a batch.
    
    Args:
        batch_id: The batch ID
        custom_llm_provider: Provider
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        BatchResult with updated status
    """
    import litellm
    
    call_kwargs = {
        'batch_id': batch_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.cancel_batch(**call_kwargs)
    
    return BatchResult(
        id=getattr(response, 'id', batch_id),
        object=getattr(response, 'object', 'batch'),
        status=getattr(response, 'status', 'cancelling'),
    )


async def abatch_cancel(
    batch_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> BatchResult:
    """
    Async: Cancel a batch.
    
    See batch_cancel() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'batch_id': batch_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.acancel_batch(**call_kwargs)
    
    return BatchResult(
        id=getattr(response, 'id', batch_id),
        object=getattr(response, 'object', 'batch'),
        status=getattr(response, 'status', 'cancelling'),
    )
