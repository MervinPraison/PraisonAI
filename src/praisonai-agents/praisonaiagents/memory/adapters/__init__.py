"""
Memory Adapters for PraisonAI.

This module provides concrete implementations of MemoryProtocol
for different backends, following the adapter pattern used in knowledge/.

Adapters:
- sqlite_adapter: SQLite-based memory storage
- chromadb_adapter: ChromaDB vector memory storage
- mongodb_adapter: MongoDB document storage
- redis_adapter: Redis in-memory storage
- postgres_adapter: PostgreSQL storage
"""

from .sqlite_adapter import SqliteMemoryAdapter

__all__ = [
    'SqliteMemoryAdapter',
]