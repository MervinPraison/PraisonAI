"""
ConversationStore implementations for session and message persistence.

Supported backends:
- PostgreSQL (postgres)
- MySQL (mysql)
- SQLite (sqlite)
- SingleStore (singlestore)
- Supabase (supabase)
- SurrealDB (surrealdb)
"""

from typing import TYPE_CHECKING

__all__ = [
    "ConversationStore",
    "ConversationSession",
    "ConversationMessage",
]

def __getattr__(name: str):
    if name in ("ConversationStore", "ConversationSession", "ConversationMessage"):
        from .base import ConversationStore, ConversationSession, ConversationMessage
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
