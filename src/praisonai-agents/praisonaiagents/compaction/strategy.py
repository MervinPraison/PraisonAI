"""
Compaction Strategies for PraisonAI Agents.
"""

from enum import Enum


class CompactionStrategy(str, Enum):
    """Strategy for compacting context."""
    TRUNCATE = "truncate"      # Remove oldest messages
    SUMMARIZE = "summarize"    # Summarize old messages
    SLIDING = "sliding"        # Sliding window of recent messages
    SMART = "smart"            # Intelligent selection based on relevance
