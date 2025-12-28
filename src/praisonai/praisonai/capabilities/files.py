"""
Files Capabilities Module

Provides file upload and management functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict, Literal, BinaryIO


@dataclass
class FileResult:
    """Result from file operations."""
    id: str
    object: str = "file"
    bytes: Optional[int] = None
    created_at: Optional[int] = None
    filename: Optional[str] = None
    purpose: Optional[str] = None
    status: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def file_create(
    file: Union[str, bytes, BinaryIO],
    purpose: Literal["assistants", "batch", "fine-tune"] = "assistants",
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> FileResult:
    """
    Upload a file for use with assistants, batch, or fine-tuning.
    
    Args:
        file: File path, bytes, or file-like object
        purpose: Purpose of the file ("assistants", "batch", "fine-tune")
        custom_llm_provider: Provider ("openai", "azure", "vertex_ai", "bedrock")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        FileResult with file ID and metadata
        
    Example:
        >>> result = file_create("./data.jsonl", purpose="batch")
        >>> print(result.id)
    """
    import litellm
    
    file_obj = file
    if isinstance(file, str):
        file_obj = open(file, 'rb')
    
    try:
        call_kwargs = {
            'file': file_obj,
            'purpose': purpose,
            'custom_llm_provider': custom_llm_provider,
            'timeout': timeout,
        }
        
        if api_key:
            call_kwargs['api_key'] = api_key
        if api_base:
            call_kwargs['api_base'] = api_base
        
        call_kwargs.update(kwargs)
        
        response = litellm.create_file(**call_kwargs)
        
        return FileResult(
            id=getattr(response, 'id', ''),
            object=getattr(response, 'object', 'file'),
            bytes=getattr(response, 'bytes', None),
            created_at=getattr(response, 'created_at', None),
            filename=getattr(response, 'filename', None),
            purpose=getattr(response, 'purpose', purpose),
            status=getattr(response, 'status', None),
            metadata=metadata or {},
        )
    finally:
        if isinstance(file, str) and hasattr(file_obj, 'close'):
            file_obj.close()


async def afile_create(
    file: Union[str, bytes, BinaryIO],
    purpose: Literal["assistants", "batch", "fine-tune"] = "assistants",
    custom_llm_provider: str = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> FileResult:
    """
    Async: Upload a file for use with assistants, batch, or fine-tuning.
    
    See file_create() for full documentation.
    """
    import litellm
    
    file_obj = file
    if isinstance(file, str):
        file_obj = open(file, 'rb')
    
    try:
        call_kwargs = {
            'file': file_obj,
            'purpose': purpose,
            'custom_llm_provider': custom_llm_provider,
            'timeout': timeout,
        }
        
        if api_key:
            call_kwargs['api_key'] = api_key
        if api_base:
            call_kwargs['api_base'] = api_base
        
        call_kwargs.update(kwargs)
        
        response = await litellm.acreate_file(**call_kwargs)
        
        return FileResult(
            id=getattr(response, 'id', ''),
            object=getattr(response, 'object', 'file'),
            bytes=getattr(response, 'bytes', None),
            created_at=getattr(response, 'created_at', None),
            filename=getattr(response, 'filename', None),
            purpose=getattr(response, 'purpose', purpose),
            status=getattr(response, 'status', None),
            metadata=metadata or {},
        )
    finally:
        if isinstance(file, str) and hasattr(file_obj, 'close'):
            file_obj.close()


def file_list(
    purpose: Optional[str] = None,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[FileResult]:
    """
    List uploaded files.
    
    Args:
        purpose: Filter by purpose
        custom_llm_provider: Provider
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        List of FileResult objects
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
    }
    
    if purpose:
        call_kwargs['purpose'] = purpose
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.file_list(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            results.append(FileResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'file'),
                bytes=getattr(item, 'bytes', None),
                created_at=getattr(item, 'created_at', None),
                filename=getattr(item, 'filename', None),
                purpose=getattr(item, 'purpose', None),
                status=getattr(item, 'status', None),
            ))
    
    return results


async def afile_list(
    purpose: Optional[str] = None,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[FileResult]:
    """
    Async: List uploaded files.
    
    See file_list() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
    }
    
    if purpose:
        call_kwargs['purpose'] = purpose
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.afile_list(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            results.append(FileResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'file'),
                bytes=getattr(item, 'bytes', None),
                created_at=getattr(item, 'created_at', None),
                filename=getattr(item, 'filename', None),
                purpose=getattr(item, 'purpose', None),
                status=getattr(item, 'status', None),
            ))
    
    return results


def file_retrieve(
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> FileResult:
    """
    Retrieve a file by ID.
    
    Args:
        file_id: The file ID
        custom_llm_provider: Provider
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        FileResult with file metadata
    """
    import litellm
    
    call_kwargs = {
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.file_retrieve(**call_kwargs)
    
    return FileResult(
        id=getattr(response, 'id', file_id),
        object=getattr(response, 'object', 'file'),
        bytes=getattr(response, 'bytes', None),
        created_at=getattr(response, 'created_at', None),
        filename=getattr(response, 'filename', None),
        purpose=getattr(response, 'purpose', None),
        status=getattr(response, 'status', None),
    )


async def afile_retrieve(
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> FileResult:
    """
    Async: Retrieve a file by ID.
    
    See file_retrieve() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.afile_retrieve(**call_kwargs)
    
    return FileResult(
        id=getattr(response, 'id', file_id),
        object=getattr(response, 'object', 'file'),
        bytes=getattr(response, 'bytes', None),
        created_at=getattr(response, 'created_at', None),
        filename=getattr(response, 'filename', None),
        purpose=getattr(response, 'purpose', None),
        status=getattr(response, 'status', None),
    )


def file_delete(
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Delete a file by ID.
    
    Args:
        file_id: The file ID
        custom_llm_provider: Provider
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        True if deleted successfully
    """
    import litellm
    
    call_kwargs = {
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.file_delete(**call_kwargs)
    
    return getattr(response, 'deleted', True)


async def afile_delete(
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> bool:
    """
    Async: Delete a file by ID.
    
    See file_delete() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.afile_delete(**call_kwargs)
    
    return getattr(response, 'deleted', True)


def file_content(
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> bytes:
    """
    Get file content by ID.
    
    Args:
        file_id: The file ID
        custom_llm_provider: Provider
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        File content as bytes
    """
    import litellm
    
    call_kwargs = {
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.file_content(**call_kwargs)
    
    if hasattr(response, 'content'):
        return response.content
    return bytes(response) if response else b''


async def afile_content(
    file_id: str,
    custom_llm_provider: str = "openai",
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> bytes:
    """
    Async: Get file content by ID.
    
    See file_content() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'file_id': file_id,
        'custom_llm_provider': custom_llm_provider,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.afile_content(**call_kwargs)
    
    if hasattr(response, 'content'):
        return response.content
    return bytes(response) if response else b''
