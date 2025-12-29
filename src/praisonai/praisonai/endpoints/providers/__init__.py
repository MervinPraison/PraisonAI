"""
Provider Adapters

Each provider adapter implements the BaseProvider interface
and handles protocol-specific details for discovery and invocation.
"""

# Lazy loading for all exports
_lazy_imports = {
    "BaseProvider": ".base",
    "RecipeProvider": ".recipe",
    "AgentsAPIProvider": ".agents_api",
    "MCPProvider": ".mcp",
    "ToolsMCPProvider": ".tools_mcp",
    "A2AProvider": ".a2a",
    "A2UProvider": ".a2u",
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
