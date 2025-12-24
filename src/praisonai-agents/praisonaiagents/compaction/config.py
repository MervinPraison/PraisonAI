"""
Compaction Configuration for PraisonAI Agents.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CompactionConfig:
    """Configuration for context compaction."""
    enabled: bool = True
    max_tokens: int = 8000
    target_tokens: int = 6000  # Target after compaction
    preserve_system: bool = True  # Always keep system messages
    preserve_recent: int = 5  # Keep last N messages
    auto_compact: bool = True  # Automatically compact when needed
