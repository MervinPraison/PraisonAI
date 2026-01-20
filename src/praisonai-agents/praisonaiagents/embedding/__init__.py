"""
Embedding module for PraisonAI Agents.

This module provides a unified embedding API that can be used throughout
the praisonaiagents package. It consolidates embedding functionality that
was previously duplicated in memory.py and knowledge.py.

Usage:
    >>> from praisonaiagents import embedding
    >>> result = embedding("Hello world")
    >>> print(result.embeddings[0][:5])
    
    >>> from praisonaiagents.embedding import embedding, EmbeddingResult
    >>> result = embedding(["Hello", "World"])
    >>> print(len(result))
    2

The module uses lazy imports to avoid loading litellm until actually needed,
ensuring zero performance impact on import time.
"""

__all__ = [
    'embedding',
    'aembedding',
    'embed',
    'aembed',
    'EmbeddingResult',
    'get_dimensions',
    'MODEL_DIMENSIONS',
    'DEFAULT_DIMENSION',
]


def __getattr__(name: str):
    """Lazy load module components to avoid importing litellm on module load."""
    if name == 'EmbeddingResult':
        from .result import EmbeddingResult
        return EmbeddingResult
    
    if name in ('embedding', 'embed'):
        from .embed import embedding
        return embedding
    
    if name in ('aembedding', 'aembed'):
        from .embed import aembedding
        return aembedding
    
    if name == 'get_dimensions':
        from .dimensions import get_dimensions
        return get_dimensions
    
    if name == 'MODEL_DIMENSIONS':
        from .dimensions import MODEL_DIMENSIONS
        return MODEL_DIMENSIONS
    
    if name == 'DEFAULT_DIMENSION':
        from .dimensions import DEFAULT_DIMENSION
        return DEFAULT_DIMENSION
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Return list of public names for dir()."""
    return list(__all__)
