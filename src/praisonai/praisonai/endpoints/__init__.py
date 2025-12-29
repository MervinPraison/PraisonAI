"""
Unified Endpoints Module

Provides unified discovery, provider adapters, and server utilities
for all PraisonAI serve features.

Provider Types:
- recipe: Recipe runner endpoints
- agents-api: Single/multi-agent HTTP API
- mcp: MCP server (stdio, http, sse)
- tools-mcp: Tools exposed as MCP server
- a2a: Agent-to-agent protocol
- a2u: Agent-to-user event stream

Architecture:
- Discovery schema is versioned and consistent across all providers
- Provider adapters abstract protocol differences
- CLI client uses unified discovery for list/describe/invoke/health
"""

# Lazy loading for all exports
_lazy_imports = {
    "DiscoveryDocument": ".discovery",
    "EndpointInfo": ".discovery",
    "ProviderInfo": ".discovery",
    "SCHEMA_VERSION": ".discovery",
    "create_discovery_document": ".discovery",
    "BaseProvider": ".providers.base",
    "RecipeProvider": ".providers.recipe",
    "AgentsAPIProvider": ".providers.agents_api",
    "MCPProvider": ".providers.mcp",
    "ToolsMCPProvider": ".providers.tools_mcp",
    "A2AProvider": ".providers.a2a",
    "A2UProvider": ".providers.a2u",
    "ProviderRegistry": ".registry",
    "get_provider": ".registry",
    "register_provider": ".registry",
    "list_provider_types": ".registry",
    "get_provider_class": ".registry",
    "create_unified_app": ".server",
    "add_discovery_routes": ".server",
}

def __getattr__(name: str):
    if name in _lazy_imports:
        module_path = _lazy_imports[name]
        import importlib
        module = importlib.import_module(module_path, package=__name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return list(_lazy_imports.keys())
