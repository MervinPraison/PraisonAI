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
