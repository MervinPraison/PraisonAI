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
    "AsyncConversationStore", 
    "ConversationSession",
    "ConversationMessage",
]

def __getattr__(name: str):
    if name in ("ConversationStore", "AsyncConversationStore", "ConversationSession", "ConversationMessage"):
        from .base import ConversationStore, AsyncConversationStore, ConversationSession, ConversationMessage
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
