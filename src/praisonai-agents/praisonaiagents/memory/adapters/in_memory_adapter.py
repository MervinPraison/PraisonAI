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
        self._max_size: int = kwargs.get("max_size", 10_000)  # Default limit
    
    def _evict_if_needed(self):
        """Evict old entries if we exceed max size (FIFO eviction)."""
        if len(self._data) > self._max_size:
            # Keep only the most recent entries
            self._data = self._data[len(self._data) - self._max_size:]

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
        self._evict_if_needed()
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
        self._evict_if_needed()
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
        # Return defensive copy to prevent external mutation of internal state
        return [dict(entry) for entry in self._data]
