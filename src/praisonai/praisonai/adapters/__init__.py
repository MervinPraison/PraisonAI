"""
PraisonAI Adapters - Implementations for core protocols.

This module provides concrete implementations of:
- Reader adapters (AutoReader, LlamaIndexReaderAdapter, MarkItDownReaderAdapter)
- Vector store adapters (ChromaAdapter, PineconeAdapter, etc.)
- Retriever implementations
- Reranker implementations
- CLI protocol adapters (C8.5: ServeHandlerAdapter, template store helper)
"""

from __future__ import annotations

from typing import Any, Optional

# Lazy loading to avoid heavy imports at package load time
_LAZY_IMPORTS = {
    # Readers
    "AutoReader": ("praisonai.adapters.readers", "AutoReader"),
    "MarkItDownReader": ("praisonai.adapters.readers", "MarkItDownReader"),
    "TextReader": ("praisonai.adapters.readers", "TextReader"),
    "DirectoryReader": ("praisonai.adapters.readers", "DirectoryReader"),
    "register_default_readers": ("praisonai.adapters.readers", "register_default_readers"),

    # Vector stores
    "ChromaVectorStore": ("praisonai.adapters.vector_stores", "ChromaVectorStore"),
    "register_default_vector_stores": ("praisonai.adapters.vector_stores", "register_default_vector_stores"),

    # Retrievers
    "BasicRetriever": ("praisonai.adapters.retrievers", "BasicRetriever"),
    "FusionRetriever": ("praisonai.adapters.retrievers", "FusionRetriever"),
    "register_default_retrievers": ("praisonai.adapters.retrievers", "register_default_retrievers"),

    # Rerankers
    "LLMReranker": ("praisonai.adapters.rerankers", "LLMReranker"),
    "register_default_rerankers": ("praisonai.adapters.rerankers", "register_default_rerankers"),
}


class ServeHandlerAdapter:
    """Adapter wrapping ``praisonai.cli.features.serve.handle_serve_command``."""

    def handle(self, args: list[str]) -> int:
        from praisonai.cli.features.serve import handle_serve_command
        return int(handle_serve_command(args) or 0)


def get_template_store() -> Optional[Any]:
    """Return template store when wrapper templates feature is available."""
    try:
        from praisonai.cli.features import templates as templates_mod
        return templates_mod
    except ImportError:
        return None


# C8.5 CLI adapters are defined in this module (not lazy) since they are
# lightweight and only trigger heavy wrapper imports when their methods run.
_LOCAL_EXPORTS = {"ServeHandlerAdapter", "get_template_store"}


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
    return list(_LAZY_IMPORTS.keys()) + sorted(_LOCAL_EXPORTS)


__all__ = list(_LAZY_IMPORTS.keys()) + sorted(_LOCAL_EXPORTS)
