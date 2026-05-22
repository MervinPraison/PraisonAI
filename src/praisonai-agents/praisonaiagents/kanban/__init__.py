"""
Kanban protocols and types for PraisonAI Agents.

This module provides the protocol contracts for kanban functionality,
allowing the wrapper (praisonai) and PraisonAIUI to share a stable
interface without coupling the core to SQLite or other heavy implementations.
"""

from praisonaiagents.kanban.protocols import (
    KanbanStoreProtocol,
    KanbanTaskProtocol,
    VALID_KANBAN_STATUSES,
)

__all__ = [
    "KanbanStoreProtocol",
    "KanbanTaskProtocol", 
    "VALID_KANBAN_STATUSES",
]