"""
PraisonAI Database - Ultra-simple persistence for agents.

RECOMMENDED (simplified import):
    from praisonaiagents import Agent, db
    # or: from praisonai import Agent, db
    
    agent = Agent(
        name="Assistant",
        db=db(database_url="postgresql://localhost/mydb"),
        session_id="my-session"
    )
    agent.chat("Hello!")  # auto-persists + can resume

DEPRECATED (will be removed in v3.0):
    from praisonai.db import PraisonDB  # Use db(...) instead

Supported backends:
- PostgreSQL, MySQL, SQLite (conversation)
- Qdrant, ChromaDB, Pinecone (knowledge/vector)
- Redis, Memory (state)
"""

import warnings

__all__ = [
    "PraisonDB",
    "PostgresDB", 
    "SQLiteDB",
    "RedisDB",
]

# Deprecation warning message
_DEPRECATION_MSG = (
    "Importing from 'praisonai.db' is deprecated and will be removed in v3.0. "
    "Use the simplified import instead:\n"
    "  from praisonaiagents import Agent, db\n"
    "  # or: from praisonai import Agent, db\n"
    "Then use: db=db(database_url='...')"
)

# Lazy imports to avoid loading heavy dependencies
def __getattr__(name: str):
    if name == "PraisonDB":
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        from .adapter import PraisonDB
        return PraisonDB
    
    if name == "PostgresDB":
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        from .adapter import PostgresDB
        return PostgresDB
    
    if name == "SQLiteDB":
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        from .adapter import SQLiteDB
        return SQLiteDB
    
    if name == "RedisDB":
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        from .adapter import RedisDB
        return RedisDB
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
