"""
Store registry for persistence backends.

Provides centralized registration and factory creation for all persistence backends
following the protocol-driven pattern used by framework adapters.
"""

import threading
from typing import Any, Callable, Dict, Optional

try:
    from importlib.metadata import entry_points
except ImportError:
    from importlib_metadata import entry_points

import logging

logger = logging.getLogger(__name__)


class StoreRegistry:
    """Registry for persistence store factories."""
    
    def __init__(self, kind: str, entry_point_group: str):
        """
        Initialize store registry.
        
        Args:
            kind: The kind of store (e.g., "conversation", "knowledge", "state")
            entry_point_group: The entry point group for external registrations
        """
        self._kind = kind
        self._factories: Dict[str, Callable[..., Any]] = {}
        self._aliases: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._register_entry_points(entry_point_group)

    def register(self, name: str, factory: Callable, *, aliases=()) -> None:
        """
        Register a store factory.
        
        Args:
            name: Backend name
            factory: Factory function that creates store instances
            aliases: Optional list of alias names for this backend
        """
        with self._lock:
            self._factories[name] = factory
            for alias in aliases:
                self._aliases[alias] = name

    def create(self, name: str, **kwargs) -> Any:
        """
        Create a store instance.
        
        Args:
            name: Backend name or alias
            **kwargs: Arguments to pass to the factory
            
        Returns:
            Store instance
            
        Raises:
            ValueError: If backend is not registered
        """
        with self._lock:
            canonical = self._aliases.get(name, name)
            factory = self._factories.get(canonical)
        
        if factory is None:
            raise ValueError(
                f"Unknown {self._kind} backend: {name}. "
                f"Registered: {sorted(self._factories)}"
            )
        
        return factory(**kwargs)

    def list_registered(self) -> list[str]:
        """List all registered backend names."""
        with self._lock:
            return sorted(self._factories.keys())

    def list_aliases(self) -> Dict[str, str]:
        """List all aliases and their target backends."""
        with self._lock:
            return dict(self._aliases)

    def _register_entry_points(self, group: str) -> None:
        """Register backends from entry points."""
        try:
            for ep in entry_points(group=group):
                try:
                    self.register(ep.name, ep.load())
                except Exception:
                    logger.warning(
                        "Failed to load %s backend %r from entry point", 
                        self._kind, ep.name, exc_info=True
                    )
        except Exception:
            # entry_points() may fail in some environments
            pass


def _register_builtin_conversation_stores():
    """Register built-in conversation stores with lazy imports."""
    
    def _postgres(url=None, **kwargs):
        from .conversation.postgres import PostgresConversationStore
        return PostgresConversationStore(url=url, **kwargs)
    
    def _async_postgres(url=None, **kwargs):
        from .conversation.async_postgres import AsyncPostgresConversationStore
        return AsyncPostgresConversationStore(url=url, **kwargs)
    
    def _mysql(url=None, **kwargs):
        from .conversation.mysql import MySQLConversationStore
        return MySQLConversationStore(url=url, **kwargs)
    
    def _async_mysql(url=None, **kwargs):
        from .conversation.async_mysql import AsyncMySQLConversationStore
        return AsyncMySQLConversationStore(url=url, **kwargs)
    
    def _sqlite(url=None, path=None, **kwargs):
        from .conversation.sqlite import SQLiteConversationStore
        return SQLiteConversationStore(path=url or path, **kwargs)
    
    def _async_sqlite(url=None, path=None, **kwargs):
        from .conversation.async_sqlite import AsyncSQLiteConversationStore
        return AsyncSQLiteConversationStore(path=url or path, **kwargs)
    
    def _json(url=None, path=None, **kwargs):
        from .conversation.json_store import JSONConversationStore
        return JSONConversationStore(path=url or path or "./praisonai_conversations", **kwargs)
    
    def _singlestore(url=None, **kwargs):
        from .conversation.singlestore import SingleStoreConversationStore
        return SingleStoreConversationStore(url=url, **kwargs)
    
    def _supabase(url=None, **kwargs):
        from .conversation.supabase import SupabaseConversationStore
        return SupabaseConversationStore(url=url, **kwargs)
    
    def _surrealdb(url=None, **kwargs):
        from .conversation.surrealdb import SurrealDBConversationStore
        return SurrealDBConversationStore(url=url, **kwargs)
    
    def _turso(url=None, **kwargs):
        from .conversation.turso import TursoConversationStore
        return TursoConversationStore(url=url, **kwargs)
    
    # Register all backends with aliases
    CONVERSATION_STORES.register("postgres", _postgres, 
        aliases=("neon", "cockroachdb", "crdb", "cockroach", "xata"))
    CONVERSATION_STORES.register("async_postgres", _async_postgres,
        aliases=("asyncpg", "postgres_async"))
    CONVERSATION_STORES.register("mysql", _mysql)
    CONVERSATION_STORES.register("async_mysql", _async_mysql,
        aliases=("aiomysql", "mysql_async"))
    CONVERSATION_STORES.register("sqlite", _sqlite)
    CONVERSATION_STORES.register("async_sqlite", _async_sqlite,
        aliases=("aiosqlite", "sqlite_async"))
    CONVERSATION_STORES.register("json", _json)
    CONVERSATION_STORES.register("singlestore", _singlestore)
    CONVERSATION_STORES.register("supabase", _supabase)
    CONVERSATION_STORES.register("surrealdb", _surrealdb)
    CONVERSATION_STORES.register("turso", _turso, aliases=("libsql",))


def _register_builtin_knowledge_stores():
    """Register built-in knowledge stores with lazy imports."""
    
    def _chroma(url=None, path=None, **kwargs):
        from .knowledge.chroma import ChromaKnowledgeStore
        return ChromaKnowledgeStore(path=url or path, **kwargs)
    
    def _qdrant(url=None, **kwargs):
        from .knowledge.qdrant import QdrantKnowledgeStore
        return QdrantKnowledgeStore(url=url, **kwargs)
    
    def _pinecone(**kwargs):
        from .knowledge.pinecone import PineconeKnowledgeStore
        return PineconeKnowledgeStore(**kwargs)
    
    def _weaviate(url=None, **kwargs):
        from .knowledge.weaviate import WeaviateKnowledgeStore
        return WeaviateKnowledgeStore(url=url, **kwargs)
    
    def _lancedb(url=None, path=None, **kwargs):
        from .knowledge.lancedb import LanceDBKnowledgeStore
        return LanceDBKnowledgeStore(path=url or path, **kwargs)
    
    def _milvus(url=None, **kwargs):
        from .knowledge.milvus import MilvusKnowledgeStore
        return MilvusKnowledgeStore(url=url, **kwargs)
    
    def _pgvector(url=None, **kwargs):
        from .knowledge.pgvector import PGVectorKnowledgeStore
        return PGVectorKnowledgeStore(url=url, **kwargs)
    
    def _redis_vector(url=None, **kwargs):
        from .knowledge.redis_vector import RedisVectorKnowledgeStore
        return RedisVectorKnowledgeStore(url=url, **kwargs)
    
    def _cassandra(**kwargs):
        from .knowledge.cassandra import CassandraKnowledgeStore
        return CassandraKnowledgeStore(**kwargs)
    
    def _clickhouse(**kwargs):
        from .knowledge.clickhouse import ClickHouseKnowledgeStore
        return ClickHouseKnowledgeStore(**kwargs)
    
    def _mongodb_vector(url=None, **kwargs):
        from .knowledge.mongodb_vector import MongoDBVectorKnowledgeStore
        return MongoDBVectorKnowledgeStore(url=url, **kwargs)
    
    KNOWLEDGE_STORES.register("chroma", _chroma, aliases=("chromadb",))
    KNOWLEDGE_STORES.register("qdrant", _qdrant)
    KNOWLEDGE_STORES.register("pinecone", _pinecone)
    KNOWLEDGE_STORES.register("weaviate", _weaviate)
    KNOWLEDGE_STORES.register("lancedb", _lancedb)
    KNOWLEDGE_STORES.register("milvus", _milvus)
    KNOWLEDGE_STORES.register("pgvector", _pgvector)
    KNOWLEDGE_STORES.register("redis", _redis_vector)
    KNOWLEDGE_STORES.register("cassandra", _cassandra)
    KNOWLEDGE_STORES.register("clickhouse", _clickhouse)
    KNOWLEDGE_STORES.register("mongodb_vector", _mongodb_vector, 
        aliases=("mongodb_atlas", "mongo_vector"))


def _register_builtin_state_stores():
    """Register built-in state stores with lazy imports."""
    
    def _redis(url=None, **kwargs):
        from .state.redis import RedisStateStore
        return RedisStateStore(url=url, **kwargs)
    
    def _dynamodb(**kwargs):
        from .state.dynamodb import DynamoDBStateStore
        return DynamoDBStateStore(**kwargs)
    
    def _firestore(**kwargs):
        from .state.firestore import FirestoreStateStore
        return FirestoreStateStore(**kwargs)
    
    def _mongodb(url=None, **kwargs):
        from .state.mongodb import MongoDBStateStore
        return MongoDBStateStore(url=url, **kwargs)
    
    def _async_mongodb(url=None, **kwargs):
        from .state.async_mongodb import AsyncMongoDBStateStore
        return AsyncMongoDBStateStore(url=url, **kwargs)
    
    def _upstash(url=None, **kwargs):
        from .state.upstash import UpstashStateStore
        return UpstashStateStore(url=url, **kwargs)
    
    def _memory(**kwargs):
        from .state.memory import MemoryStateStore
        return MemoryStateStore(**kwargs)
    
    def _gcs(bucket_name=None, bucket=None, **kwargs):
        from .state.gcs import GCSStateStore
        bucket = bucket_name or bucket
        if not bucket:
            raise ValueError("GCS state store requires 'bucket_name' option")
        return GCSStateStore(bucket_name=bucket, **kwargs)
    
    STATE_STORES.register("redis", _redis)
    STATE_STORES.register("dynamodb", _dynamodb)
    STATE_STORES.register("firestore", _firestore)
    STATE_STORES.register("mongodb", _mongodb)
    STATE_STORES.register("async_mongodb", _async_mongodb, 
        aliases=("motor", "mongodb_async"))
    STATE_STORES.register("upstash", _upstash)
    STATE_STORES.register("memory", _memory)
    STATE_STORES.register("gcs", _gcs)


# Create global registry instances
CONVERSATION_STORES = StoreRegistry("conversation", "praisonai.conversation_stores")
KNOWLEDGE_STORES = StoreRegistry("knowledge", "praisonai.knowledge_stores") 
STATE_STORES = StoreRegistry("state", "praisonai.state_stores")

# Register built-in stores
_register_builtin_conversation_stores()
_register_builtin_knowledge_stores()
_register_builtin_state_stores()