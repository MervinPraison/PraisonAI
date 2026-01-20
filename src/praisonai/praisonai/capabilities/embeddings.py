"""
Embeddings Capabilities Module

Provides text embedding functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict


@dataclass
class EmbeddingResult:
    """Result from embedding generation."""
    embeddings: List[List[float]]
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def embed(
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
    
    Args:
        input: Text or list of texts to embed
        model: Model name (e.g., "text-embedding-3-small", "text-embedding-3-large")
        dimensions: Optional output dimensions (for models that support it)
        encoding_format: "float" or "base64"
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        EmbeddingResult with embeddings list
        
    Example:
        >>> result = embed("Hello, world!")
        >>> print(len(result.embeddings[0]))
        
        >>> result = embed(["Hello", "World"], model="text-embedding-3-large")
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


# Aliases for consistency with LiteLLM naming
embedding = embed
"""Alias for embed(). Use embed() or embedding() interchangeably."""


async def aembed(
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
    
    See embed() for full documentation.
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


# Async alias for consistency with LiteLLM naming
aembedding = aembed
"""Alias for aembed(). Use aembed() or aembedding() interchangeably."""
