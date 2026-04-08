"""
Knowledge Store Adapters for PraisonAI Agents.

Provides adapter implementations for various knowledge backends.
All adapters implement KnowledgeStoreProtocol.

Adapters are now registered via the adapter registry to enable
protocol-driven knowledge backend resolution.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mem0_adapter import Mem0Adapter

# Import registry functions
from .registry import (
    register_knowledge_adapter,
    register_knowledge_factory,
    get_knowledge_adapter,
    list_knowledge_adapters,
    get_first_available_knowledge_adapter,
    has_knowledge_adapter,
)

# Import factory functions for heavy adapters
from .factories import (
    create_mem0_knowledge_adapter,
    create_mongodb_knowledge_adapter,
    create_chroma_knowledge_adapter,
    create_sqlite_knowledge_adapter,
)

# Register core adapter factories (lightweight, no heavy dependencies)
register_knowledge_factory("sqlite", create_sqlite_knowledge_adapter)

# Register heavy adapter factories (lazy-loaded via factories)
register_knowledge_factory("mem0", create_mem0_knowledge_adapter)
register_knowledge_factory("mongodb", create_mongodb_knowledge_adapter)
register_knowledge_factory("chroma", create_chroma_knowledge_adapter)

# Lazy loading for adapters (backward compatibility)
_LAZY_IMPORTS = {
    "Mem0Adapter": ("praisonaiagents.knowledge.adapters.mem0_adapter", "Mem0Adapter"),
    "MongoDBKnowledgeAdapter": ("praisonaiagents.knowledge.adapters.mongodb_adapter", "MongoDBKnowledgeAdapter"),
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
    return list(_LAZY_IMPORTS.keys()) + [
        "register_knowledge_adapter",
        "register_knowledge_factory", 
        "get_knowledge_adapter",
        "list_knowledge_adapters",
        "get_first_available_knowledge_adapter",
        "has_knowledge_adapter",
    ]


__all__ = [
    "Mem0Adapter",
    "MongoDBKnowledgeAdapter",
    # Registry functions
    "register_knowledge_adapter",
    "register_knowledge_factory",
    "get_knowledge_adapter", 
    "list_knowledge_adapters",
    "get_first_available_knowledge_adapter",
    "has_knowledge_adapter",
]
