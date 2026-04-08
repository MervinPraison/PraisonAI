"""
Memory Adapters for PraisonAI.

This module provides concrete implementations of MemoryProtocol
for different backends, following the adapter pattern used in knowledge/.

Adapters:
- sqlite_adapter: SQLite-based memory storage (core)
- in_memory_adapter: Lightweight in-memory storage (core, for testing/dev)
- chromadb_adapter: ChromaDB vector memory storage (wrapper)
- mongodb_adapter: MongoDB document storage (wrapper)
- redis_adapter: Redis in-memory storage (wrapper)
- postgres_adapter: PostgreSQL storage (wrapper)

Heavy adapters (chromadb, mongodb, etc.) are moved to wrapper package
to keep core lightweight and protocol-driven.
"""

from .sqlite_adapter import SqliteMemoryAdapter
from .in_memory_adapter import InMemoryAdapter
from .registry import (
    register_memory_adapter,
    register_memory_factory,
    get_memory_adapter,
    list_memory_adapters,
    get_first_available_memory_adapter,
    has_memory_adapter,
)
from .factories import (
    create_mem0_memory_adapter,
    create_chroma_memory_adapter,
    create_mongodb_memory_adapter,
)

# Register core adapters
register_memory_adapter("sqlite", SqliteMemoryAdapter)
register_memory_adapter("in_memory", InMemoryAdapter)

# Register heavy adapter factories (lazy-loaded)
register_memory_factory("mem0", create_mem0_memory_adapter)
register_memory_factory("chroma", create_chroma_memory_adapter)
register_memory_factory("mongodb", create_mongodb_memory_adapter)

__all__ = [
    'SqliteMemoryAdapter',
    'InMemoryAdapter',
    'register_memory_adapter',
    'register_memory_factory',
    'get_memory_adapter',
    'list_memory_adapters',
    'get_first_available_memory_adapter',
    'has_memory_adapter',
]
