"""
Auto Context Compaction Module for PraisonAI Agents.

Provides automatic context management for long conversations:
- Message summarization
- Context window management
- Token counting and limits
- Intelligent message pruning

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Compaction only runs when needed
- No overhead when context is within limits

Usage:
    from praisonaiagents.compaction import ContextCompactor, CompactionConfig
    
    # Create a compactor
    compactor = ContextCompactor(
        max_tokens=8000,
        strategy="summarize"
    )
    
    # Compact messages when needed
    compacted = compactor.compact(messages)
"""

__all__ = [
    # Core classes
    "ContextCompactor",
    "CompactionConfig",
    # Strategies
    "CompactionStrategy",
    # Results
    "CompactionResult",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name == "ContextCompactor":
        from .compactor import ContextCompactor
        return ContextCompactor
    
    if name == "CompactionConfig":
        from .config import CompactionConfig
        return CompactionConfig
    
    if name == "CompactionStrategy":
        from .strategy import CompactionStrategy
        return CompactionStrategy
    
    if name == "CompactionResult":
        from .result import CompactionResult
        return CompactionResult
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
