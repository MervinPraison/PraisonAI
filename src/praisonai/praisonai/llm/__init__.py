"""
LLM Module for PraisonAI CLI Wrapper.

This module provides LLM provider registry and utilities for the CLI wrapper.
The core LLM functionality is in praisonaiagents.llm.
"""

from .._lazy_cache import lazy_get

_LAZY_ATTRS = {
    "LLMProviderRegistry":      lambda: __import__("praisonai.llm.registry", fromlist=["LLMProviderRegistry"]).LLMProviderRegistry,
    "get_default_llm_registry": lambda: __import__("praisonai.llm.registry", fromlist=["get_default_llm_registry"]).get_default_llm_registry,
    "register_llm_provider":    lambda: __import__("praisonai.llm.registry", fromlist=["register_llm_provider"]).register_llm_provider,
    "unregister_llm_provider":  lambda: __import__("praisonai.llm.registry", fromlist=["unregister_llm_provider"]).unregister_llm_provider,
    "has_llm_provider":         lambda: __import__("praisonai.llm.registry", fromlist=["has_llm_provider"]).has_llm_provider,
    "list_llm_providers":       lambda: __import__("praisonai.llm.registry", fromlist=["list_llm_providers"]).list_llm_providers,
    "create_llm_provider":      lambda: __import__("praisonai.llm.registry", fromlist=["create_llm_provider"]).create_llm_provider,
    "parse_model_string":       lambda: __import__("praisonai.llm.registry", fromlist=["parse_model_string"]).parse_model_string,
    "_reset_default_registry":  lambda: __import__("praisonai.llm.registry", fromlist=["_reset_default_registry"])._reset_default_registry,
    # Gateway providers
    "OpenRouterProvider":       lambda: __import__("praisonai.llm.gateways", fromlist=["OpenRouterProvider"]).OpenRouterProvider,
    "LiteLLMProxyProvider":     lambda: __import__("praisonai.llm.gateways", fromlist=["LiteLLMProxyProvider"]).LiteLLMProxyProvider,
    "CustomGatewayProvider":    lambda: __import__("praisonai.llm.gateways", fromlist=["CustomGatewayProvider"]).CustomGatewayProvider,
    "register_gateway_providers": lambda: __import__("praisonai.llm.gateways", fromlist=["register_gateway_providers"]).register_gateway_providers,
}

def __getattr__(name):
    """Lazy load LLM registry classes."""
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = lazy_get(f"llm:{name}", _LAZY_ATTRS[name])
    if value is None:
        raise AttributeError(f"module {__name__!r} cannot load attribute {name!r} due to import failure")
    return value


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
    # Gateway providers
    "OpenRouterProvider",
    "LiteLLMProxyProvider",
    "CustomGatewayProvider",
    "register_gateway_providers",
]

# NOTE: Gateway providers ("openrouter/...", "litellm-proxy/...", etc.) are
# registered lazily on first registry access (see get_default_llm_registry() in
# registry.py), not eagerly on import. This keeps `create_llm_provider(...)`
# behaviour unchanged while avoiding the gateway + registry + importlib.metadata
# import cost on the config-only hot path (e.g. build_config_list).


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
    try:
        from praisonaiagents.utils.deprecation import warn_deprecated_param
        warn_deprecated_param(
            "praisonai.llm.embedding()",
            since="1.0.0",
            removal="2.0.0",
            alternative="use 'from praisonai import embed' or 'from praisonai.capabilities import embed' instead",
            details="The new embed() returns EmbeddingResult with metadata",
            stacklevel=3
        )
    except ImportError:
        # Fallback if deprecation module not available
        import warnings
        warnings.warn(
            "praisonai.llm.embedding() is deprecated. Use 'from praisonai import embed' instead.",
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

