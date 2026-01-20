"""
Core embedding functions.

This module provides the main embedding() and aembedding() functions
that wrap LiteLLM's embedding API with a consistent interface.
"""

from typing import Optional, Union, List, Any, Dict

from .result import EmbeddingResult


def embedding(
    input: Union[str, List[str]],
    model: str = "text-embedding-3-small",
    dimensions: Optional[int] = None,
    encoding_format: str = "float",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> EmbeddingResult:
    """
    Generate embeddings for text using LiteLLM.
    
    This is the primary embedding function that supports all LiteLLM
    embedding providers (OpenAI, Azure, Cohere, Voyage, etc.).
    
    Args:
        input: Text or list of texts to embed
        model: Model name (e.g., "text-embedding-3-small", "text-embedding-3-large")
        dimensions: Optional output dimensions (for models that support it)
        encoding_format: "float" or "base64"
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        **kwargs: Additional arguments passed to litellm.embedding()
        
    Returns:
        EmbeddingResult with embeddings list, model, usage, and metadata
        
    Example:
        >>> from praisonaiagents import embedding
        >>> result = embedding("Hello, world!")
        >>> print(len(result.embeddings[0]))
        1536
        
        >>> result = embedding(["Hello", "World"], model="text-embedding-3-large")
        >>> print(len(result.embeddings))
        2
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'input': input,
        'encoding_format': encoding_format,
        'timeout': timeout,
    }
    
    if dimensions:
        call_kwargs['dimensions'] = dimensions
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.embedding(**call_kwargs)
    
    embeddings = []
    if hasattr(response, 'data'):
        for item in response.data:
            if isinstance(item, dict):
                embeddings.append(item.get('embedding', []))
            else:
                embeddings.append(getattr(item, 'embedding', []))
    
    usage = None
    if hasattr(response, 'usage'):
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    return EmbeddingResult(
        embeddings=embeddings,
        model=model,
        usage=usage,
        metadata=metadata or {},
    )


async def aembedding(
    input: Union[str, List[str]],
    model: str = "text-embedding-3-small",
    dimensions: Optional[int] = None,
    encoding_format: str = "float",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> EmbeddingResult:
    """
    Async: Generate embeddings for text using LiteLLM.
    
    This is the async version of embedding() for use in async contexts.
    See embedding() for full documentation.
    
    Example:
        >>> from praisonaiagents import aembedding
        >>> result = await aembedding("Hello, world!")
        >>> print(len(result.embeddings[0]))
        1536
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'input': input,
        'encoding_format': encoding_format,
        'timeout': timeout,
    }
    
    if dimensions:
        call_kwargs['dimensions'] = dimensions
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.aembedding(**call_kwargs)
    
    embeddings = []
    if hasattr(response, 'data'):
        for item in response.data:
            if isinstance(item, dict):
                embeddings.append(item.get('embedding', []))
            else:
                embeddings.append(getattr(item, 'embedding', []))
    
    usage = None
    if hasattr(response, 'usage'):
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    return EmbeddingResult(
        embeddings=embeddings,
        model=model,
        usage=usage,
        metadata=metadata or {},
    )


# Aliases for backwards compatibility and OpenAI naming convention
embed = embedding
"""Alias for embedding(). Use embedding() or embed() interchangeably."""

aembed = aembedding
"""Alias for aembedding(). Use aembedding() or aembed() interchangeably."""
