"""
PraisonAI RAG - Retrieval Augmented Generation Module.

This module provides a thin orchestration layer over Knowledge for RAG workflows.
Knowledge handles indexing/retrieval; RAG adds answer generation with citations.

Usage:
    from praisonaiagents.rag import RAG, RAGConfig, RAGResult, Citation
    
    # With existing Knowledge
    rag = RAG(knowledge=my_knowledge)
    result = rag.query("What is the main finding?")
    print(result.answer)
    for citation in result.citations:
        print(f"  [{citation.id}] {citation.source}")

All imports are lazy to avoid performance impact when RAG is not used.
"""

from typing import TYPE_CHECKING

# Lazy loading to avoid import overhead
_LAZY_IMPORTS = {
    # Models
    "Citation": ("praisonaiagents.rag.models", "Citation"),
    "ContextPack": ("praisonaiagents.rag.models", "ContextPack"),
    "RAGResult": ("praisonaiagents.rag.models", "RAGResult"),
    "RAGConfig": ("praisonaiagents.rag.models", "RAGConfig"),
    "RetrievalStrategy": ("praisonaiagents.rag.models", "RetrievalStrategy"),
    # Unified retrieval config (Agent-first)
    "RetrievalConfig": ("praisonaiagents.rag.retrieval_config", "RetrievalConfig"),
    "RetrievalPolicy": ("praisonaiagents.rag.retrieval_config", "RetrievalPolicy"),
    "CitationsMode": ("praisonaiagents.rag.retrieval_config", "CitationsMode"),
    "create_retrieval_config": ("praisonaiagents.rag.retrieval_config", "create_retrieval_config"),
    # Protocols
    "ContextBuilderProtocol": ("praisonaiagents.rag.protocols", "ContextBuilderProtocol"),
    "CitationFormatterProtocol": ("praisonaiagents.rag.protocols", "CitationFormatterProtocol"),
    # Pipeline (internal - use Agent for primary access)
    "RAG": ("praisonaiagents.rag.pipeline", "RAG"),
    # Context utilities
    "build_context": ("praisonaiagents.rag.context", "build_context"),
    "truncate_context": ("praisonaiagents.rag.context", "truncate_context"),
    "deduplicate_chunks": ("praisonaiagents.rag.context", "deduplicate_chunks"),
}

_cache = {}


def __getattr__(name: str):
    """Lazy load RAG components."""
    if name in _cache:
        return _cache[name]
    
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        _cache[name] = value
        return value
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """List available attributes."""
    return list(_LAZY_IMPORTS.keys())


__all__ = list(_LAZY_IMPORTS.keys())

if TYPE_CHECKING:
    from .models import Citation, ContextPack, RAGResult, RAGConfig
    from .protocols import ContextBuilderProtocol, CitationFormatterProtocol
    from .pipeline import RAG
    from .context import build_context, truncate_context, deduplicate_chunks
