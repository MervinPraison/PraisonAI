"""
In-Memory Memory Adapter for PraisonAI.

Lightweight in-memory adapter for testing and development.
No dependencies required - stores data as plain Python lists.
"""

from typing import Any, Dict, List, Optional


class InMemoryAdapter:
    """
    Lightweight in-memory adapter for testing and development.

    Stores short-term and long-term memories as plain Python lists.
    Data is not persisted across process restarts.

    Usage:
        adapter = InMemoryAdapter()
        adapter.store_short_term("hello", {"source": "test"})
        results = adapter.search_short_term("hello")
    """

    def __init__(self, **kwargs) -> None:
        self._data: List[Dict[str, Any]] = []

    def store_short_term(
        self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        entry: Dict[str, Any] = {
            "id": str(len(self._data)),
            "text": text,
            "type": "short",
            "metadata": metadata,
        }
        self._data.append(entry)
        return entry["id"]

    def search_short_term(
        self, query: str, limit: int = 5, **kwargs
    ) -> List[Dict[str, Any]]:
        results = [
            e
            for e in self._data
            if e["type"] == "short" and query.lower() in e["text"].lower()
        ]
        return results[:limit]

    def store_long_term(
        self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        entry: Dict[str, Any] = {
            "id": str(len(self._data)),
            "text": text,
            "type": "long",
            "metadata": metadata,
        }
        self._data.append(entry)
        return entry["id"]

    def search_long_term(
        self, query: str, limit: int = 5, **kwargs
    ) -> List[Dict[str, Any]]:
        results = [
            e
            for e in self._data
            if e["type"] == "long" and query.lower() in e["text"].lower()
        ]
        return results[:limit]

    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        return list(self._data)
