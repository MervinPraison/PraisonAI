"""
Background Configuration for PraisonAI Agents.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BackgroundConfig:
    """Configuration for background task execution."""
    max_concurrent_tasks: int = 5
    default_timeout: Optional[float] = None  # None = no timeout
    auto_cleanup: bool = True  # Auto-remove completed tasks
    cleanup_delay: float = 300.0  # Seconds to keep completed tasks
    enable_notifications: bool = True
    log_progress: bool = True
