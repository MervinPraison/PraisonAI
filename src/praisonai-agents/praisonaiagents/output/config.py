"""
Output Configuration for PraisonAI Agents.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class OutputConfig:
    """Configuration for output formatting."""
    enabled: bool = True
    default_format: str = "markdown"  # markdown, plain, json
    max_length: Optional[int] = None
    truncate_long_responses: bool = False
    include_metadata: bool = False
