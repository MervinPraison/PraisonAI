"""
Indexer module for Fast Context.

Provides file and symbol indexing capabilities for fast code search.
"""

def __getattr__(name):
    """Lazy load indexer classes."""
    if name == "FileIndexer":
        from .file_indexer import FileIndexer
        return FileIndexer
    elif name == "SymbolIndexer":
        from .symbol_indexer import SymbolIndexer
        return SymbolIndexer
    elif name == "Symbol":
        from .symbol_indexer import Symbol
        return Symbol
    elif name == "SymbolType":
        from .symbol_indexer import SymbolType
        return SymbolType
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["FileIndexer", "SymbolIndexer", "Symbol", "SymbolType"]
