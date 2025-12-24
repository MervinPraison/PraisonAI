"""
Policy Configuration for PraisonAI Agents.
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class PolicyConfig:
    """Configuration for the policy engine."""
    enabled: bool = True
    default_action: str = "allow"  # Default action when no policy matches
    log_decisions: bool = True
    strict_mode: bool = False  # If True, deny when no policy matches
