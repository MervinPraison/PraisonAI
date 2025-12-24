"""
Factory functions for creating store instances.

Provides lazy loading of backend implementations to avoid importing
unused dependencies.
"""

import logging
from typing import Any, Dict, Optional

from .config import PersistenceConfig

logger = logging.getLogger(__name__)


def create_conversation_store(
    backend: str,
    url: Optional[str] = None,
    **options: Any
):
    """
    Create a ConversationStore instance.
    
    Args:
        backend: Backend type (postgres, mysql, sqlite, singlestore, supabase, surrealdb)
        url: Connection URL
        **options: Backend-specific options
    
    Returns:
        ConversationStore instance
    
    Example:
        store = create_conversation_store(
            "postgres",
            url="postgresql://localhost:5432/praisonai"
        )
    """
    backend = backend.lower()
    
    if backend == "postgres":
        from .conversation.postgres import PostgresConversationStore
        return PostgresConversationStore(url=url, **options)
    
    elif backend == "mysql":
        from .conversation.mysql import MySQLConversationStore
        return MySQLConversationStore(url=url, **options)
    
    elif backend == "sqlite":
        from .conversation.sqlite import SQLiteConversationStore
        path = url or options.pop("path", None)
        return SQLiteConversationStore(path=path, **options)
    
    elif backend == "singlestore":
        from .conversation.singlestore import SingleStoreConversationStore
        return SingleStoreConversationStore(url=url, **options)
    
    elif backend == "supabase":
        from .conversation.supabase import SupabaseConversationStore
        return SupabaseConversationStore(url=url, **options)
    
    elif backend == "surrealdb":
        from .conversation.surrealdb import SurrealDBConversationStore
        return SurrealDBConversationStore(url=url, **options)
    
    else:
        raise ValueError(
            f"Unknown conversation store backend: {backend}. "
            f"Supported: postgres, mysql, sqlite, singlestore, supabase, surrealdb"
        )


def create_knowledge_store(
    backend: str,
    url: Optional[str] = None,
    **options: Any
):
    """
    Create a KnowledgeStore instance.
    
    Args:
        backend: Backend type (qdrant, pinecone, chroma, weaviate, lancedb, milvus, pgvector, redis, cassandra, clickhouse)
        url: Connection URL
        **options: Backend-specific options
    
    Returns:
        KnowledgeStore instance
    
    Example:
        store = create_knowledge_store(
            "qdrant",
            url="http://localhost:6333"
        )
    """
    backend = backend.lower()
    
    if backend == "qdrant":
        from .knowledge.qdrant import QdrantKnowledgeStore
        return QdrantKnowledgeStore(url=url, **options)
    
    elif backend == "pinecone":
        from .knowledge.pinecone import PineconeKnowledgeStore
        return PineconeKnowledgeStore(**options)
    
    elif backend == "chroma":
        from .knowledge.chroma import ChromaKnowledgeStore
        path = url or options.pop("path", None)
        return ChromaKnowledgeStore(path=path, **options)
    
    elif backend == "weaviate":
        from .knowledge.weaviate import WeaviateKnowledgeStore
        return WeaviateKnowledgeStore(url=url, **options)
    
    elif backend == "lancedb":
        from .knowledge.lancedb import LanceDBKnowledgeStore
        path = url or options.pop("path", None)
        return LanceDBKnowledgeStore(path=path, **options)
    
    elif backend == "milvus":
        from .knowledge.milvus import MilvusKnowledgeStore
        return MilvusKnowledgeStore(url=url, **options)
    
    elif backend == "pgvector":
        from .knowledge.pgvector import PGVectorKnowledgeStore
        return PGVectorKnowledgeStore(url=url, **options)
    
    elif backend == "redis":
        from .knowledge.redis_vector import RedisVectorKnowledgeStore
        return RedisVectorKnowledgeStore(url=url, **options)
    
    elif backend == "cassandra":
        from .knowledge.cassandra import CassandraKnowledgeStore
        return CassandraKnowledgeStore(**options)
    
    elif backend == "clickhouse":
        from .knowledge.clickhouse import ClickHouseKnowledgeStore
        return ClickHouseKnowledgeStore(**options)
    
    else:
        raise ValueError(
            f"Unknown knowledge store backend: {backend}. "
            f"Supported: qdrant, pinecone, chroma, weaviate, lancedb, milvus, pgvector, redis, cassandra, clickhouse"
        )


def create_state_store(
    backend: str,
    url: Optional[str] = None,
    **options: Any
):
    """
    Create a StateStore instance.
    
    Args:
        backend: Backend type (redis, dynamodb, firestore, mongodb, upstash, memory)
        url: Connection URL
        **options: Backend-specific options
    
    Returns:
        StateStore instance
    
    Example:
        store = create_state_store(
            "redis",
            url="redis://localhost:6379"
        )
    """
    backend = backend.lower()
    
    if backend == "redis":
        from .state.redis import RedisStateStore
        return RedisStateStore(url=url, **options)
    
    elif backend == "dynamodb":
        from .state.dynamodb import DynamoDBStateStore
        return DynamoDBStateStore(**options)
    
    elif backend == "firestore":
        from .state.firestore import FirestoreStateStore
        return FirestoreStateStore(**options)
    
    elif backend == "mongodb":
        from .state.mongodb import MongoDBStateStore
        return MongoDBStateStore(url=url, **options)
    
    elif backend == "upstash":
        from .state.upstash import UpstashStateStore
        return UpstashStateStore(url=url, **options)
    
    elif backend == "memory":
        from .state.memory import MemoryStateStore
        return MemoryStateStore(**options)
    
    else:
        raise ValueError(
            f"Unknown state store backend: {backend}. "
            f"Supported: redis, dynamodb, firestore, mongodb, upstash, memory"
        )


def create_stores_from_config(config: PersistenceConfig) -> Dict[str, Any]:
    """
    Create all configured stores from a PersistenceConfig.
    
    Returns:
        Dict with keys: conversation, knowledge, state (values may be None)
    """
    stores = {
        "conversation": None,
        "knowledge": None,
        "state": None,
    }
    
    if config.conversation_store:
        stores["conversation"] = create_conversation_store(
            config.conversation_store,
            url=config.conversation_url,
            **config.conversation_options
        )
    
    if config.knowledge_store:
        stores["knowledge"] = create_knowledge_store(
            config.knowledge_store,
            url=config.knowledge_url,
            **config.knowledge_options
        )
    
    if config.state_store:
        stores["state"] = create_state_store(
            config.state_store,
            url=config.state_url,
            **config.state_options
        )
    
    return stores
