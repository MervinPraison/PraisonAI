"""
In-Memory Memory Adapter for PraisonAI.

Lightweight in-memory adapter for testing and development.
No dependencies required - stores data as plain Python lists.
"""

import threading
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
        self._next_id: int = 0  # Monotonic counter to prevent ID collisions after eviction
        # Guards the non-atomic id-increment + append + eviction sequence. Async
        # task/knowledge paths offload writes via ``asyncio.to_thread``, so
        # parallel callbacks can hit this shared adapter on different worker
        # threads concurrently. A re-entrant lock keeps every mutation atomic
        # (no duplicate ids / lost entries) at negligible cost for the common
        # single-threaded case.
        self._lock = threading.RLock()
    
    def _evict_if_needed(self):
        """Evict old entries if we exceed max size (FIFO eviction)."""
        if len(self._data) > self._max_size:
            # Keep only the most recent entries
            self._data = self._data[len(self._data) - self._max_size:]

    def store_short_term(
        self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        with self._lock:
            entry: Dict[str, Any] = {
                "id": str(self._next_id),
                "text": text,
                "type": "short",
                "metadata": metadata,
            }
            self._next_id += 1
            self._data.append(entry)
            self._evict_if_needed()
            return entry["id"]

    def search_short_term(
        self, query: str, limit: int = 5, **kwargs
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = [
                e
                for e in self._data
                if e["type"] == "short" and query.lower() in e["text"].lower()
            ]
            return results[:limit]

    def store_long_term(
        self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        with self._lock:
            entry: Dict[str, Any] = {
                "id": str(self._next_id),
                "text": text,
                "type": "long",
                "metadata": metadata,
            }
            self._next_id += 1
            self._data.append(entry)
            self._evict_if_needed()
            return entry["id"]

    def search_long_term(
        self, query: str, limit: int = 5, **kwargs
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results = [
                e
                for e in self._data
                if e["type"] == "long" and query.lower() in e["text"].lower()
            ]
            return results[:limit]

    def delete_memory(self, memory_id: str, tier: Optional[str] = None, **kwargs) -> bool:
        """Delete a memory by ID. Returns True if an entry was removed.

        ``tier`` ("short" or "long") optionally scopes the delete to a single
        tier. IDs here are globally unique (shared monotonic counter), so tier
        is only used to preserve the caller's scope, never for disambiguation.
        """
        with self._lock:
            before = len(self._data)
            self._data = [
                e
                for e in self._data
                if not (
                    e.get("id") == str(memory_id)
                    and (tier is None or e.get("type") == tier)
                )
            ]
            return len(self._data) < before

    def reset_short_term(self) -> None:
        """Clear all short-term memories."""
        with self._lock:
            self._data = [e for e in self._data if e.get("type") != "short"]

    def reset_long_term(self) -> None:
        """Clear all long-term memories."""
        with self._lock:
            self._data = [e for e in self._data if e.get("type") != "long"]

    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        with self._lock:
            # Return defensive copy to prevent external mutation of internal state
            return [dict(entry) for entry in self._data]
