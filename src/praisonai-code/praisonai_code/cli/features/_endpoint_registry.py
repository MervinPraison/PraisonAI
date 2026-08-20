"""
Registry for endpoint provider types.

Maps endpoint types to their invocation methods (lazy-loaded).
Extensible: third-party endpoint types can register via entry points.
"""

from __future__ import annotations

from typing import Callable, Any

from ..._registry import PluginRegistry


# Built-in endpoint types - return callables that will be bound to the class instance
def _recipe_loader():
    def invoke_recipe(self, endpoint_name: str, input_data: Any, config: dict, parsed: dict):
        return self._invoke_recipe(endpoint_name, input_data, config, parsed)
    return invoke_recipe


def _agents_api_loader():
    def invoke_agents_api(self, endpoint_name: str, input_data: Any, config: dict, parsed: dict):
        return self._invoke_agents_api(endpoint_name, input_data, config, parsed)
    return invoke_agents_api


def _mcp_loader():
    def invoke_mcp(self, endpoint_name: str, input_data: Any, config: dict, parsed: dict):
        return self._invoke_mcp(endpoint_name, input_data, config, parsed)
    return invoke_mcp


def _a2a_loader():
    def invoke_a2a(self, endpoint_name: str, input_data: Any, config: dict, parsed: dict):
        return self._invoke_a2a(endpoint_name, input_data, config, parsed)
    return invoke_a2a


def _a2u_loader():
    def invoke_a2u(self, endpoint_name: str, input_data: Any, config: dict, parsed: dict):
        return self._invoke_a2u(endpoint_name, input_data, config, parsed)
    return invoke_a2u


def _openai_compat_loader():
    # Returns the provider class; ``EndpointProviderRegistry.resolve`` adapts it
    # to the CLI dispatch signature.
    from praisonai.endpoints.providers.openai_compat import OpenAICompatProvider
    return OpenAICompatProvider


# Built-in endpoint types with lazy loading
_BUILTIN_ENDPOINTS = {
    "recipe": _recipe_loader,
    "agents-api": _agents_api_loader,
    "mcp": _mcp_loader,
    "tools-mcp": _mcp_loader,  # Alias for mcp
    "a2a": _a2a_loader,
    "a2u": _a2u_loader,
    "openai-compat": _openai_compat_loader,
}


# Canonical / deprecated entry-point group spellings. Kept in sync with
# ``praisonai.endpoints.registry``: both readers must scan the same group or a
# plugin is visible to one surface and invisible to the other.
ENTRY_POINT_GROUP = "praisonai.endpoint_providers"
LEGACY_ENTRY_POINT_GROUPS = ("praisonai.endpoints.providers",)


def _adapt_provider_class(provider_cls):
    """Wrap a ``praisonai.endpoints.providers.base.BaseProvider`` subclass into
    the ``(handler, name, input_data, config, parsed)`` callable this CLI
    dispatch table expects.

    Plugins publish provider *classes* (the public contract of
    ``praisonai.endpoints``); the built-ins here are bound CLI methods.
    Adapting lets one entry-point group serve both readers.
    """

    def invoke(handler, endpoint_name, input_data, config, parsed):
        provider = provider_cls(
            base_url=parsed.get("url") or handler.base_url,
            api_key=parsed.get("api_key") or handler.api_key,
        )
        result = provider.invoke(
            endpoint_name,
            input_data,
            config,
            stream=bool(parsed.get("stream")),
        )
        payload = {"status": 200 if result.ok else 500, "data": result.data}
        if result.error:
            payload["error"] = {"message": result.error}
        return handler._handle_invoke_result(payload, endpoint_name, parsed)

    return invoke


class EndpointProviderRegistry(PluginRegistry):
    """Registry for endpoint provider types."""

    def __init__(self):
        super().__init__(
            entry_point_group=ENTRY_POINT_GROUP,
            builtins=_BUILTIN_ENDPOINTS,
            legacy_entry_point_groups=LEGACY_ENTRY_POINT_GROUPS,
        )
        # Built-ins are the CLI's own dispatch methods and must win: a plugin
        # may add a new provider type but must not hijack a shipped one.
        for name, loader in _BUILTIN_ENDPOINTS.items():
            self._add_loader(name, loader)

    def resolve(self, name):
        target = super().resolve(name)
        if isinstance(target, type):
            # An endpoint provider class published under the entry-point group.
            return _adapt_provider_class(target)
        return target