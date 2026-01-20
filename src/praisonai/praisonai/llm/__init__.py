"""
LLM Module for PraisonAI CLI Wrapper.

This module provides LLM provider registry and utilities for the CLI wrapper.
The core LLM functionality is in praisonaiagents.llm.
"""

# Lazy loading for performance
_lazy_cache = {}


def __getattr__(name):
    """Lazy load LLM registry classes."""
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "LLMProviderRegistry":
        from .registry import LLMProviderRegistry
        _lazy_cache[name] = LLMProviderRegistry
        return LLMProviderRegistry
    elif name == "get_default_llm_registry":
        from .registry import get_default_llm_registry
        _lazy_cache[name] = get_default_llm_registry
        return get_default_llm_registry
    elif name == "register_llm_provider":
        from .registry import register_llm_provider
        _lazy_cache[name] = register_llm_provider
        return register_llm_provider
    elif name == "unregister_llm_provider":
        from .registry import unregister_llm_provider
        _lazy_cache[name] = unregister_llm_provider
        return unregister_llm_provider
    elif name == "has_llm_provider":
        from .registry import has_llm_provider
        _lazy_cache[name] = has_llm_provider
        return has_llm_provider
    elif name == "list_llm_providers":
        from .registry import list_llm_providers
        _lazy_cache[name] = list_llm_providers
        return list_llm_providers
    elif name == "create_llm_provider":
        from .registry import create_llm_provider
        _lazy_cache[name] = create_llm_provider
        return create_llm_provider
    elif name == "parse_model_string":
        from .registry import parse_model_string
        _lazy_cache[name] = parse_model_string
        return parse_model_string
    elif name == "_reset_default_registry":
        from .registry import _reset_default_registry
        _lazy_cache[name] = _reset_default_registry
        return _reset_default_registry
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "LLMProviderRegistry",
    "get_default_llm_registry",
    "register_llm_provider",
    "unregister_llm_provider",
    "has_llm_provider",
    "list_llm_providers",
    "create_llm_provider",
    "parse_model_string",
    "embedding",
]


def embedding(text, model="text-embedding-3-small", **kwargs):
    """
    Get embedding vector for text.
    
    .. deprecated::
        Use `from praisonai import embed` or `from praisonai.capabilities import embed` instead.
        This function returns raw vectors; the new embed() returns EmbeddingResult with metadata.
    
    Args:
        text: Text string or list of strings to embed
        model: Embedding model name (default: text-embedding-3-small)
        **kwargs: Additional arguments passed to litellm.embedding()
    
    Returns:
        List[float] for single text, or List[List[float]] for multiple texts
    
    Example:
        from praisonai.llm import embedding
        
        # Single text
        emb = embedding("Hello world")
        
        # Multiple texts
        embs = embedding(["Hello", "World"])
        
        # Different model
        emb = embedding("Hello", model="text-embedding-3-large")
    
    Note:
        Requires litellm. Install with: pip install praisonai[llm]
    """
    import warnings
    warnings.warn(
        "praisonai.llm.embedding() is deprecated. "
        "Use 'from praisonai import embed' or 'from praisonai.capabilities import embed' instead. "
        "The new embed() returns EmbeddingResult with metadata.",
        DeprecationWarning,
        stacklevel=2
    )
    
    try:
        import litellm
    except ImportError:
        raise ImportError(
            "litellm is required for embedding(). "
            "Install with: pip install praisonai[llm] or pip install litellm"
        )
    
    # Handle single string vs list
    if isinstance(text, str):
        input_data = [text]
        single = True
    else:
        input_data = list(text)
        single = False
    
    response = litellm.embedding(model=model, input=input_data, **kwargs)
    
    embeddings = [item["embedding"] for item in response.data]
    
    return embeddings[0] if single else embeddings

