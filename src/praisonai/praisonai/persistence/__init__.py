"""
PraisonAI Persistence Layer

Provides database integrations for:
- Conversation history persistence (ConversationStore)
- Knowledge storage and retrieval (KnowledgeStore)
- Session/state management (StateStore)

All integrations use lazy loading to avoid importing unused dependencies.

Supported Backends (22 total):
- ConversationStore (6): postgres, mysql, sqlite, singlestore, supabase, surrealdb
- KnowledgeStore (10): qdrant, pinecone, chroma, weaviate, lancedb, milvus, pgvector, redis, cassandra, clickhouse
- StateStore (6): redis, dynamodb, firestore, mongodb, upstash, memory
"""

from typing import TYPE_CHECKING

__all__ = [
    # Base interfaces
    "ConversationStore",
    "ConversationSession",
    "ConversationMessage",
    "KnowledgeStore",
    "KnowledgeDocument",
    "StateStore",
    # Orchestrator
    "PersistenceOrchestrator",
    # Factory functions
    "create_conversation_store",
    "create_knowledge_store",
    "create_state_store",
    "create_stores_from_config",
    # Config
    "PersistenceConfig",
    # Agent hooks
    "wrap_agent_with_persistence",
    "PersistentAgent",
    "create_persistent_session",
]

# Lazy imports to avoid loading dependencies until needed
def __getattr__(name: str):
    if name in ("ConversationStore", "ConversationSession", "ConversationMessage"):
        from .conversation.base import ConversationStore, ConversationSession, ConversationMessage
        return locals()[name]
    
    if name in ("KnowledgeStore", "KnowledgeDocument"):
        from .knowledge.base import KnowledgeStore, KnowledgeDocument
        return locals()[name]
    
    if name == "StateStore":
        from .state.base import StateStore
        return StateStore
    
    if name == "PersistenceOrchestrator":
        from .orchestrator import PersistenceOrchestrator
        return PersistenceOrchestrator
    
    if name == "PersistenceConfig":
        from .config import PersistenceConfig
        return PersistenceConfig
    
    if name == "create_conversation_store":
        from .factory import create_conversation_store
        return create_conversation_store
    
    if name == "create_knowledge_store":
        from .factory import create_knowledge_store
        return create_knowledge_store
    
    if name == "create_state_store":
        from .factory import create_state_store
        return create_state_store
    
    if name == "create_stores_from_config":
        from .factory import create_stores_from_config
        return create_stores_from_config
    
    if name in ("wrap_agent_with_persistence", "PersistentAgent", "create_persistent_session"):
        from .hooks.agent_hooks import wrap_agent_with_persistence, PersistentAgent, create_persistent_session
        return locals()[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
