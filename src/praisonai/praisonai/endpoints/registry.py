"""
Provider Registry

Central registry for provider adapters — unified with the rest of the wrapper.
"""

from __future__ import annotations

import threading
from typing import Any, List, Optional, Type

from .providers.base import BaseProvider
from .._registry import PluginRegistry


def _recipe_loader():
    from .providers.recipe import RecipeProvider
    return RecipeProvider


def _agents_api_loader():
    from .providers.agents_api import AgentsAPIProvider
    return AgentsAPIProvider


def _mcp_loader():
    from .providers.mcp import MCPProvider
    return MCPProvider


def _tools_mcp_loader():
    from .providers.tools_mcp import ToolsMCPProvider
    return ToolsMCPProvider


def _a2a_loader():
    from .providers.a2a import A2AProvider
    return A2AProvider


def _a2u_loader():
    from .providers.a2u import A2UProvider
    return A2UProvider


_BUILTIN_PROVIDERS = {
    "recipe":      _recipe_loader,
    "agents-api":  _agents_api_loader,
    "mcp":         _mcp_loader,
    "tools-mcp":   _tools_mcp_loader,
    "a2a":         _a2a_loader,
    "a2u":         _a2u_loader,
}


class ProviderRegistry(PluginRegistry[Type[BaseProvider]]):
    """Endpoint provider registry — unified with the rest of the wrapper."""

    def __init__(self) -> None:
        super().__init__(
            entry_point_group="praisonai.endpoint_providers",
            builtins=_BUILTIN_PROVIDERS,
        )

    def get(
        self,
        provider_type: str,
        base_url: str = "http://localhost:8765",
        api_key: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[BaseProvider]:
        try:
            cls = self.resolve(provider_type)
        except ValueError:
            return None
        return cls(base_url=base_url, api_key=api_key, **kwargs)


_default_registry: Optional[ProviderRegistry] = None
_default_lock = threading.Lock()


def get_default_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        with _default_lock:
            if _default_registry is None:
                _default_registry = ProviderRegistry()
    return _default_registry


# Module-level functions kept for backwards compat — now delegate to the registry
def register_provider(provider_type: str, provider_class: Type[BaseProvider]) -> None:
    get_default_registry().register(provider_type, provider_class)


def get_provider(provider_type, base_url="http://localhost:8765", api_key=None, **kwargs):
    return get_default_registry().get(provider_type, base_url=base_url, api_key=api_key, **kwargs)


def list_provider_types() -> List[str]:
    return get_default_registry().list_names()


def get_provider_class(provider_type: str) -> Optional[Type[BaseProvider]]:
    try:
        return get_default_registry().resolve(provider_type)
    except ValueError:
        return None
