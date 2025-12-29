"""
Provider Registry

Central registry for provider adapters.
"""

from typing import Dict, List, Optional, Type

from .providers.base import BaseProvider


# Global provider registry
_providers: Dict[str, Type[BaseProvider]] = {}


def register_provider(provider_type: str, provider_class: Type[BaseProvider]) -> None:
    """
    Register a provider class.
    
    Args:
        provider_type: Provider type identifier
        provider_class: Provider class to register
    """
    _providers[provider_type] = provider_class


def get_provider(
    provider_type: str,
    base_url: str = "http://localhost:8765",
    api_key: Optional[str] = None,
    **kwargs,
) -> Optional[BaseProvider]:
    """
    Get a provider instance by type.
    
    Args:
        provider_type: Provider type identifier
        base_url: Base URL for the provider
        api_key: Optional API key
        **kwargs: Additional provider-specific arguments
        
    Returns:
        Provider instance or None if not found
    """
    # Lazy register built-in providers
    _ensure_providers_registered()
    
    if provider_type not in _providers:
        return None
    
    return _providers[provider_type](base_url=base_url, api_key=api_key, **kwargs)


def list_provider_types() -> List[str]:
    """
    List all registered provider types.
    
    Returns:
        List of provider type identifiers
    """
    _ensure_providers_registered()
    return list(_providers.keys())


def get_provider_class(provider_type: str) -> Optional[Type[BaseProvider]]:
    """
    Get a provider class by type.
    
    Args:
        provider_type: Provider type identifier
        
    Returns:
        Provider class or None if not found
    """
    _ensure_providers_registered()
    return _providers.get(provider_type)


def _ensure_providers_registered() -> None:
    """Ensure built-in providers are registered."""
    if _providers:
        return
    
    # Lazy import and register built-in providers
    from .providers.recipe import RecipeProvider
    from .providers.agents_api import AgentsAPIProvider
    from .providers.mcp import MCPProvider
    from .providers.tools_mcp import ToolsMCPProvider
    from .providers.a2a import A2AProvider
    from .providers.a2u import A2UProvider
    
    register_provider("recipe", RecipeProvider)
    register_provider("agents-api", AgentsAPIProvider)
    register_provider("mcp", MCPProvider)
    register_provider("tools-mcp", ToolsMCPProvider)
    register_provider("a2a", A2AProvider)
    register_provider("a2u", A2UProvider)


class ProviderRegistry:
    """
    Provider registry class for managing provider instances.
    
    This class provides a more object-oriented interface to the provider registry.
    """
    
    def __init__(self):
        """Initialize the registry."""
        _ensure_providers_registered()
    
    def get(
        self,
        provider_type: str,
        base_url: str = "http://localhost:8765",
        api_key: Optional[str] = None,
        **kwargs,
    ) -> Optional[BaseProvider]:
        """Get a provider instance."""
        return get_provider(provider_type, base_url, api_key, **kwargs)
    
    def register(self, provider_type: str, provider_class: Type[BaseProvider]) -> None:
        """Register a provider class."""
        register_provider(provider_type, provider_class)
    
    def list_types(self) -> List[str]:
        """List all provider types."""
        return list_provider_types()
    
    def get_class(self, provider_type: str) -> Optional[Type[BaseProvider]]:
        """Get a provider class."""
        return get_provider_class(provider_type)
