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


# Built-in endpoint types with lazy loading
_BUILTIN_ENDPOINTS = {
    "recipe": _recipe_loader,
    "agents-api": _agents_api_loader,
    "mcp": _mcp_loader,
    "tools-mcp": _mcp_loader,  # Alias for mcp
    "a2a": _a2a_loader,
    "a2u": _a2u_loader,
}


class EndpointProviderRegistry(PluginRegistry):
    """Registry for endpoint provider types."""
    
    def __init__(self):
        super().__init__(
            entry_point_group="praisonai.endpoints.providers",
            builtins=_BUILTIN_ENDPOINTS
        )