"""
Thinking Configuration for PraisonAI Agents.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ThinkingConfig:
    """Configuration for extended thinking."""
    enabled: bool = True
    default_budget_tokens: int = 8000
    max_budget_tokens: int = 32000
    default_time_seconds: Optional[float] = None
    adaptive: bool = True  # Adjust budget based on task complexity
    log_thinking: bool = False  # Log thinking process
