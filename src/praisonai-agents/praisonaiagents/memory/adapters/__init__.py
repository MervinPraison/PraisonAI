"""
Memory Adapters for PraisonAI.

This module provides concrete implementations of MemoryProtocol
for different backends, following the adapter pattern used in knowledge/.

Adapters:
- sqlite_adapter: SQLite-based memory storage (core)
- chromadb_adapter: ChromaDB vector memory storage (wrapper)
- mongodb_adapter: MongoDB document storage (wrapper)
- redis_adapter: Redis in-memory storage (wrapper)
- postgres_adapter: PostgreSQL storage (wrapper)

Heavy adapters (chromadb, mongodb, etc.) are moved to wrapper package
to keep core lightweight and protocol-driven.
"""

from .sqlite_adapter import SqliteMemoryAdapter
from .registry import (
    register_memory_adapter,
    register_memory_factory,
    get_memory_adapter,
    list_memory_adapters,
    get_first_available_memory_adapter,
)

# Register core adapters
register_memory_adapter("sqlite", SqliteMemoryAdapter)

# Create in-memory adapter for testing
class InMemoryAdapter:
    """Lightweight in-memory adapter for testing and development."""
    
    def __init__(self, **kwargs):
        self._data = []
    
    def store_short_term(self, text: str, metadata=None, **kwargs) -> str:
        entry = {"id": str(len(self._data)), "text": text, "type": "short", "metadata": metadata}
        self._data.append(entry)
        return entry["id"]
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs):
        # Simple text matching
        results = [entry for entry in self._data if entry["type"] == "short" and query.lower() in entry["text"].lower()]
        return results[:limit]
    
    def store_long_term(self, text: str, metadata=None, **kwargs) -> str:
        entry = {"id": str(len(self._data)), "text": text, "type": "long", "metadata": metadata}
        self._data.append(entry)
        return entry["id"]
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs):
        # Simple text matching
        results = [entry for entry in self._data if entry["type"] == "long" and query.lower() in entry["text"].lower()]
        return results[:limit]
    
    def get_all_memories(self, **kwargs):
        return self._data

register_memory_adapter("in_memory", InMemoryAdapter)

__all__ = [
    'SqliteMemoryAdapter',
    'InMemoryAdapter',
    'register_memory_adapter',
    'register_memory_factory', 
    'get_memory_adapter',
    'list_memory_adapters',
    'get_first_available_memory_adapter',
]