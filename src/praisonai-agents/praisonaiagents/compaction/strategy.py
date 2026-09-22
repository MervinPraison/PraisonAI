"""
Compaction strategies for context management.
"""

from enum import Enum


class CompactionStrategy(str, Enum):
    """Available compaction strategies."""
    
    TRUNCATE = "truncate"
    SLIDING = "sliding"
    SUMMARIZE = "summarize"
    SMART = "smart"
    LLM_SUMMARIZE = "llm_summarize"  # Use LLM for summarization
    PRUNE = "prune"  # Remove old tool outputs

    @classmethod
    def from_policy_value(cls, value: str) -> "CompactionStrategy":
        """Map a context-policy strategy value to a compactor strategy.

        The policy layer (``context.protocols.CompactionStrategy``) uses a
        different member set than the compactor. This is the single source of
        truth for translating between the two; keep it here rather than
        duplicating the mapping at each call site.
        """
        return {
            "truncate": cls.TRUNCATE,
            "summarise": cls.SUMMARIZE,
            "drop_oldest_tools": cls.PRUNE,
            "sliding_window": cls.SLIDING,
        }.get(value, cls.PRUNE)
