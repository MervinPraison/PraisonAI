"""
Compaction Result for PraisonAI Agents.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any

from .strategy import CompactionStrategy


@dataclass
class CompactionResult:
    """Result of a compaction operation."""
    original_tokens: int
    compacted_tokens: int
    messages_removed: int
    messages_kept: int
    strategy_used: CompactionStrategy
    summary: str = ""
    
    @property
    def tokens_saved(self) -> int:
        """Get number of tokens saved."""
        return self.original_tokens - self.compacted_tokens
    
    @property
    def compression_ratio(self) -> float:
        """Get compression ratio."""
        if self.original_tokens == 0:
            return 0.0
        return self.compacted_tokens / self.original_tokens
    
    @property
    def was_compacted(self) -> bool:
        """Check if compaction occurred."""
        return self.messages_removed > 0 or self.tokens_saved > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_tokens": self.original_tokens,
            "compacted_tokens": self.compacted_tokens,
            "tokens_saved": self.tokens_saved,
            "messages_removed": self.messages_removed,
            "messages_kept": self.messages_kept,
            "strategy_used": self.strategy_used.value,
            "compression_ratio": self.compression_ratio,
            "summary": self.summary
        }
