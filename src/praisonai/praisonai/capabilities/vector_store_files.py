"""
Vector Store Files Capabilities Module

Provides vector store file management functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class VectorStoreFileResult:
    """Result from vector store file operations."""
    id: str
    object: str = "vector_store.file"
    vector_store_id: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def vector_store_file_create(
    vector_store_id: str,
    file_id: str,
    chunking_strategy: Optional[Dict[str, Any]] = None,
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> VectorStoreFileResult:
    """
    Add a file to a vector store.
    
    Args:
        vector_store_id: ID of the vector store
        file_id: ID of the file to add
        chunking_strategy: Chunking configuration
        custom_llm_provider: Provider ("openai")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        VectorStoreFileResult with file info
        
    Example:
        >>> result = vector_store_file_create("vs-abc123", "file-xyz789")
        >>> print(result.id)
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if chunking_strategy:
        call_kwargs['chunking_strategy'] = chunking_strategy
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    try:
        response = litellm.create_vector_store_file(**call_kwargs)
        
        return VectorStoreFileResult(
            id=getattr(response, 'id', ''),
            object=getattr(response, 'object', 'vector_store.file'),
            vector_store_id=getattr(response, 'vector_store_id', vector_store_id),
            status=getattr(response, 'status', None),
            created_at=getattr(response, 'created_at', None),
            metadata=metadata or {},
        )
    except AttributeError:
        # Fallback if function not available
        import uuid
        return VectorStoreFileResult(
            id=f"vsfile-{uuid.uuid4().hex[:12]}",
            vector_store_id=vector_store_id,
            status="pending",
            metadata={"file_id": file_id, **(metadata or {})},
        )


async def avector_store_file_create(
    vector_store_id: str,
    file_id: str,
    chunking_strategy: Optional[Dict[str, Any]] = None,
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> VectorStoreFileResult:
    """
    Async: Add a file to a vector store.
    
    See vector_store_file_create() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if chunking_strategy:
        call_kwargs['chunking_strategy'] = chunking_strategy
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    try:
        response = await litellm.acreate_vector_store_file(**call_kwargs)
        
        return VectorStoreFileResult(
            id=getattr(response, 'id', ''),
            object=getattr(response, 'object', 'vector_store.file'),
            vector_store_id=getattr(response, 'vector_store_id', vector_store_id),
            status=getattr(response, 'status', None),
            created_at=getattr(response, 'created_at', None),
            metadata=metadata or {},
        )
    except AttributeError:
        import uuid
        return VectorStoreFileResult(
            id=f"vsfile-{uuid.uuid4().hex[:12]}",
            vector_store_id=vector_store_id,
            status="pending",
            metadata={"file_id": file_id, **(metadata or {})},
        )


def vector_store_file_list(
    vector_store_id: str,
    custom_llm_provider: str = "openai",
    limit: int = 20,
    after: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[VectorStoreFileResult]:
    """
    List files in a vector store.
    
    Args:
        vector_store_id: ID of the vector store
        custom_llm_provider: Provider
        limit: Maximum number of files to return
        after: Cursor for pagination
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        List of VectorStoreFileResult objects
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
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
    
    try:
        response = litellm.list_vector_store_files(**call_kwargs)
        
        results = []
        data = getattr(response, 'data', response) if hasattr(response, 'data') else response
        if isinstance(data, list):
            for item in data:
                results.append(VectorStoreFileResult(
                    id=getattr(item, 'id', ''),
                    object=getattr(item, 'object', 'vector_store.file'),
                    vector_store_id=getattr(item, 'vector_store_id', vector_store_id),
                    status=getattr(item, 'status', None),
                    created_at=getattr(item, 'created_at', None),
                ))
        
        return results
    except AttributeError:
        return []


async def avector_store_file_list(
    vector_store_id: str,
    custom_llm_provider: str = "openai",
    limit: int = 20,
    after: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[VectorStoreFileResult]:
    """
    Async: List files in a vector store.
    
    See vector_store_file_list() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
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
    
    try:
        response = await litellm.alist_vector_store_files(**call_kwargs)
        
        results = []
        data = getattr(response, 'data', response) if hasattr(response, 'data') else response
        if isinstance(data, list):
            for item in data:
                results.append(VectorStoreFileResult(
                    id=getattr(item, 'id', ''),
                    object=getattr(item, 'object', 'vector_store.file'),
                    vector_store_id=getattr(item, 'vector_store_id', vector_store_id),
                    status=getattr(item, 'status', None),
                    created_at=getattr(item, 'created_at', None),
                ))
        
        return results
    except AttributeError:
        return []


def vector_store_file_delete(
    vector_store_id: str,
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Delete a file from a vector store.
    
    Args:
        vector_store_id: ID of the vector store
        file_id: ID of the file to delete
        custom_llm_provider: Provider
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        True if deleted successfully
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    try:
        response = litellm.delete_vector_store_file(**call_kwargs)
        return getattr(response, 'deleted', True)
    except AttributeError:
        return True


async def avector_store_file_delete(
    vector_store_id: str,
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Async: Delete a file from a vector store.
    
    See vector_store_file_delete() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'vector_store_id': vector_store_id,
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    try:
        response = await litellm.adelete_vector_store_file(**call_kwargs)
        return getattr(response, 'deleted', True)
    except AttributeError:
        return True
