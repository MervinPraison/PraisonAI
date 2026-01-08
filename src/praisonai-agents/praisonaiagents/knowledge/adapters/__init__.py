"""
Knowledge Store Adapters for PraisonAI Agents.

Provides adapter implementations for various knowledge backends.
All adapters implement KnowledgeStoreProtocol.

Adapters are lazy-loaded to avoid importing heavy dependencies.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mem0_adapter import Mem0Adapter

# Lazy loading for adapters
_LAZY_IMPORTS = {
    "Mem0Adapter": ("praisonaiagents.knowledge.adapters.mem0_adapter", "Mem0Adapter"),
}


def __getattr__(name: str):
    """Lazy load adapters."""
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """List available attributes."""
    return list(_LAZY_IMPORTS.keys())


__all__ = [
    "Mem0Adapter",
]
