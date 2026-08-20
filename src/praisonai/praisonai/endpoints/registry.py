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


def _openai_compat_loader():
    from .providers.openai_compat import OpenAICompatProvider
    return OpenAICompatProvider


_BUILTIN_PROVIDERS = {
    "recipe":         _recipe_loader,
    "agents-api":     _agents_api_loader,
    "mcp":            _mcp_loader,
    "tools-mcp":      _tools_mcp_loader,
    "a2a":            _a2a_loader,
    "a2u":            _a2u_loader,
    # Shipped provider that was never registered, so `--type openai-compat`
    # silently ran as a recipe.
    "openai-compat":  _openai_compat_loader,
}


#: Canonical entry-point group for third-party endpoint providers. A plugin
#: publishes ``name = your_pkg:YourProvider`` (a :class:`BaseProvider`
#: subclass) under this group.
ENTRY_POINT_GROUP = "praisonai.endpoint_providers"

#: Historical misspelling, still honoured but warned about. It was read by
#: ``praisonai_code.cli.features._endpoint_registry`` while this module read
#: ``praisonai.endpoint_providers``, so which reader saw a plugin depended on
#: which spelling its author happened to guess.
LEGACY_ENTRY_POINT_GROUPS = ("praisonai.endpoints.providers",)


class ProviderRegistry(PluginRegistry[Type[BaseProvider]]):
    """Endpoint provider registry — unified with the rest of the wrapper."""

    def __init__(self) -> None:
        super().__init__(
            entry_point_group=ENTRY_POINT_GROUP,
            builtins=_BUILTIN_PROVIDERS,
            legacy_entry_point_groups=LEGACY_ENTRY_POINT_GROUPS,
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
            # Distinguish between missing provider vs import failure
            if provider_type.lower() not in self.list_all_names():
                return None
            raise
        return cls(base_url=base_url, api_key=api_key, **kwargs)

    # Backward compatibility methods - forward to parent class methods
    def list_types(self) -> List[str]:
        """List available provider types. Backward compatibility alias for list_names()."""
        return self.list_names()

    def get_class(self, provider_type: str) -> Optional[Type[BaseProvider]]:
        """Get provider class by type. Backward compatibility alias for resolve()."""
        try:
            return self.resolve(provider_type)
        except ValueError:
            return None


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
    registry = get_default_registry()
    try:
        return registry.resolve(provider_type)
    except ValueError:
        # Distinguish between missing provider vs import failure
        if provider_type.lower() not in registry.list_all_names():
            return None
        raise
