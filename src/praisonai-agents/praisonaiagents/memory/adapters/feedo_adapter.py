"""
Feedo Memory Adapter for PraisonAI.

Integrates the Feedo decentralized search network as a memory backend for
PraisonAI agents. It follows the same protocol-driven adapter pattern as the
other backends (sqlite, in_memory, chroma, mem0, ...).

Feedo is a decentralized storage + semantic search network. Your identity is
your crypto wallet (``did:feedo:0x...``) — no accounts, no KYC. Memories are
stored as vectors on the P2P network.

Configuration (in the agent ``memory`` dict)::

    from praisonaiagents import Agent

    agent = Agent(
        name="Assistant",
        memory={
            "provider": "feedo",
            "config": {
                "usage_key": "0x...",    # delegated usage key (only this is required)
                "user_id": "user123",    # optional: isolate memories per user
                "private": True,         # optional: private (default) or public
            },
        },
    )

The ``did`` is auto-resolved from the usage key's delegation, so it does not
need to be provided explicitly.
"""

from typing import Any, Dict, List, Optional


class FeedoMemoryAdapter:
    """Memory adapter backed by the Feedo decentralized search network.

    Implements the PraisonAI ``MemoryProtocol`` (short/long-term store + search)
    plus the optional delete/reset helpers.
    """

    def __init__(self, **kwargs: Any) -> None:
        try:
            from feedo import FeedoMemory
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "feedo-sdk is not installed. Run: pip install feedo-sdk"
            ) from e

        self._memory = FeedoMemory(
            usage_key=kwargs.get("usage_key"),
            private_key=kwargs.get("private_key"),
            did=kwargs.get("did"),
            user_id=kwargs.get("user_id"),
            private=kwargs.get("private", True),
            search_seeds=kwargs.get("search_seeds"),
            consensus_seeds=kwargs.get("consensus_seeds"),
            storage_seeds=kwargs.get("storage_seeds"),
        )

    # ------------------------------------------------------------------
    # MemoryProtocol
    # ------------------------------------------------------------------

    def store_short_term(
        self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> str:
        """Store content in short-term memory. Returns the memory id."""
        return self._memory.add_short(text, metadata)

    def search_short_term(
        self, query: str, limit: int = 5, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Search short-term memory."""
        return self._memory.search_short(query, limit=limit)

    def store_long_term(
        self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> str:
        """Store content in long-term memory. Returns the memory id."""
        return self._memory.add_long(text, metadata)

    def search_long_term(
        self, query: str, limit: int = 5, **kwargs: Any
    ) -> List[Dict[str, Any]]:
        """Search long-term memory."""
        return self._memory.search_long(query, limit=limit)

    def get_all_memories(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Return all stored memories (short + long)."""
        return self._memory.get_all_memories()

    # ------------------------------------------------------------------
    # DeletableMemoryProtocol
    # ------------------------------------------------------------------

    def delete_memory(self, memory_id: str, tier: Optional[str] = None, **kwargs: Any) -> bool:
        """Delete a specific memory by id.

        Feedo currently supports namespace-level deletion only; per-item delete
        is not available yet, so this returns ``False``.
        """
        return False

    # ------------------------------------------------------------------
    # ResettableMemoryProtocol
    # ------------------------------------------------------------------

    def reset_short_term(self) -> None:
        """Clear all short-term memories."""
        self._memory.clear_short()

    def reset_long_term(self) -> None:
        """Clear all long-term memories."""
        self._memory.clear_long()


def create_feedo_memory_adapter(**kwargs: Any) -> FeedoMemoryAdapter:
    """Factory function for the Feedo memory adapter (lazy-loads feedo-sdk)."""
    return FeedoMemoryAdapter(**kwargs)
