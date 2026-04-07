"""
Git-Native Agent Protocol (GNAP) for PraisonAI.

This module provides protocols for durable task persistence using Git repositories
as coordination layers. Following PraisonAI's protocol-driven architecture.

Core concepts:
- Tasks are persisted as JSON files in Git commits
- Task progress is tracked through Git history  
- Multiple agents can coordinate via shared repositories
- Git's durability ensures tasks survive system failures
"""

from .protocols import (
    GNAPProtocol,
    GNAPRepositoryProtocol,
    GNAPTaskProtocol,
    GNAPTaskSpec,
    GNAPTaskStatus,
)
from .models import (
    GNAPTask,
    GNAPConfig,
    TaskDependency,
)

__all__ = [
    "GNAPProtocol",
    "GNAPRepositoryProtocol", 
    "GNAPTaskProtocol",
    "GNAPTaskSpec",
    "GNAPTaskStatus",
    "GNAPTask",
    "GNAPConfig",
    "TaskDependency",
]