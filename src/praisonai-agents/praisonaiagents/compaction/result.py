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
    
    # Anti-thrashing and optimization info
    savings_pct: float = field(default=0.0, init=False)  # Percentage of tokens saved (computed)
    tool_results_pruned: int = 0  # Number of tool results deduplicated/pruned
    previous_summary_reused: bool = False  # Whether iterative summary was used
    was_skipped_due_to_low_savings: bool = False  # Whether compaction was skipped due to anti-thrashing
    
    def __post_init__(self):
        """Initialize computed fields after construction."""
        self.calculate_savings_pct()
    
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
    
    def calculate_savings_pct(self) -> None:
        """Calculate and set the savings percentage."""
        if self.original_tokens > 0:
            self.savings_pct = (self.tokens_saved / self.original_tokens) * 100.0
        else:
            self.savings_pct = 0.0
    
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
            "savings_pct": self.savings_pct,
            "tool_results_pruned": self.tool_results_pruned,
            "previous_summary_reused": self.previous_summary_reused,
            "was_skipped_due_to_low_savings": self.was_skipped_due_to_low_savings,
            "summary": self.summary
        }
