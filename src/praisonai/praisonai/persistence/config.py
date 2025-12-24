"""
Configuration handling for PraisonAI persistence layer.

Supports configuration via:
- Environment variables
- Config file (YAML/JSON)
- CLI arguments
- Direct Python API
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Environment variable mappings
ENV_VARS = {
    # Conversation stores
    "conversation_store": "PRAISONAI_CONVERSATION_STORE",
    "conversation_url": "PRAISONAI_CONVERSATION_URL",
    # Knowledge stores
    "knowledge_store": "PRAISONAI_KNOWLEDGE_STORE",
    "knowledge_url": "PRAISONAI_KNOWLEDGE_URL",
    # State stores
    "state_store": "PRAISONAI_STATE_STORE",
    "state_url": "PRAISONAI_STATE_URL",
    # Common
    "session_id": "PRAISONAI_SESSION_ID",
    "user_id": "PRAISONAI_USER_ID",
    # PostgreSQL
    "postgres_url": "POSTGRES_URL",
    "postgres_host": "POSTGRES_HOST",
    "postgres_port": "POSTGRES_PORT",
    "postgres_database": "POSTGRES_DATABASE",
    "postgres_user": "POSTGRES_USER",
    "postgres_password": "POSTGRES_PASSWORD",
    # Qdrant
    "qdrant_url": "QDRANT_URL",
    "qdrant_host": "QDRANT_HOST",
    "qdrant_port": "QDRANT_PORT",
    "qdrant_api_key": "QDRANT_API_KEY",
    # Redis
    "redis_url": "REDIS_URL",
    "redis_host": "REDIS_HOST",
    "redis_port": "REDIS_PORT",
    "redis_password": "REDIS_PASSWORD",
    # Pinecone
    "pinecone_api_key": "PINECONE_API_KEY",
    "pinecone_environment": "PINECONE_ENVIRONMENT",
    "pinecone_index": "PINECONE_INDEX",
    # ChromaDB
    "chroma_path": "CHROMA_DB_PATH",
    "chroma_host": "CHROMA_HOST",
    "chroma_port": "CHROMA_PORT",
    # Weaviate
    "weaviate_url": "WEAVIATE_URL",
    "weaviate_api_key": "WEAVIATE_API_KEY",
    # Milvus
    "milvus_host": "MILVUS_HOST",
    "milvus_port": "MILVUS_PORT",
    "milvus_token": "MILVUS_TOKEN",
    # MongoDB
    "mongodb_url": "MONGODB_URL",
    "mongodb_database": "MONGODB_DATABASE",
    # DynamoDB
    "aws_region": "AWS_REGION",
    "dynamodb_table": "DYNAMODB_TABLE",
    # Firestore
    "google_credentials": "GOOGLE_APPLICATION_CREDENTIALS",
    "firestore_project": "FIRESTORE_PROJECT",
    # Upstash
    "upstash_redis_url": "UPSTASH_REDIS_URL",
    "upstash_redis_token": "UPSTASH_REDIS_TOKEN",
    "upstash_vector_url": "UPSTASH_VECTOR_URL",
    "upstash_vector_token": "UPSTASH_VECTOR_TOKEN",
    # Supabase
    "supabase_url": "SUPABASE_URL",
    "supabase_key": "SUPABASE_KEY",
    # SurrealDB
    "surrealdb_url": "SURREALDB_URL",
    "surrealdb_namespace": "SURREALDB_NS",
    "surrealdb_database": "SURREALDB_DB",
    # MySQL
    "mysql_url": "MYSQL_URL",
    "mysql_host": "MYSQL_HOST",
    "mysql_port": "MYSQL_PORT",
    "mysql_database": "MYSQL_DATABASE",
    "mysql_user": "MYSQL_USER",
    "mysql_password": "MYSQL_PASSWORD",
    # SingleStore
    "singlestore_url": "SINGLESTORE_URL",
    # ClickHouse
    "clickhouse_host": "CLICKHOUSE_HOST",
    "clickhouse_port": "CLICKHOUSE_PORT",
    "clickhouse_user": "CLICKHOUSE_USER",
    "clickhouse_password": "CLICKHOUSE_PASSWORD",
    # Cassandra
    "cassandra_hosts": "CASSANDRA_HOSTS",
    "cassandra_keyspace": "CASSANDRA_KEYSPACE",
    # LanceDB
    "lancedb_path": "LANCEDB_PATH",
    "lancedb_uri": "LANCEDB_URI",
}

# Supported backends
CONVERSATION_BACKENDS = ["postgres", "mysql", "sqlite", "singlestore", "supabase", "surrealdb"]
KNOWLEDGE_BACKENDS = ["qdrant", "pinecone", "chroma", "weaviate", "lancedb", "milvus", "pgvector", "redis", "cassandra", "clickhouse"]
STATE_BACKENDS = ["redis", "dynamodb", "firestore", "mongodb", "upstash", "memory"]


@dataclass
class PersistenceConfig:
    """
    Configuration for PraisonAI persistence layer.
    
    Example:
        config = PersistenceConfig(
            conversation_store="postgres",
            conversation_url="postgresql://localhost:5432/praisonai",
            knowledge_store="qdrant",
            knowledge_url="http://localhost:6333",
            state_store="redis",
            state_url="redis://localhost:6379",
        )
    """
    # Store backends
    conversation_store: Optional[str] = None
    conversation_url: Optional[str] = None
    conversation_options: Dict[str, Any] = field(default_factory=dict)
    
    knowledge_store: Optional[str] = None
    knowledge_url: Optional[str] = None
    knowledge_options: Dict[str, Any] = field(default_factory=dict)
    
    state_store: Optional[str] = None
    state_url: Optional[str] = None
    state_options: Dict[str, Any] = field(default_factory=dict)
    
    # Session/user context
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    
    # General options
    auto_create_tables: bool = True
    lazy_init: bool = True
    
    @classmethod
    def from_env(cls) -> "PersistenceConfig":
        """Create config from environment variables."""
        return cls(
            conversation_store=os.getenv(ENV_VARS["conversation_store"]),
            conversation_url=os.getenv(ENV_VARS["conversation_url"]) or os.getenv(ENV_VARS["postgres_url"]),
            knowledge_store=os.getenv(ENV_VARS["knowledge_store"]),
            knowledge_url=os.getenv(ENV_VARS["knowledge_url"]) or os.getenv(ENV_VARS["qdrant_url"]),
            state_store=os.getenv(ENV_VARS["state_store"]),
            state_url=os.getenv(ENV_VARS["state_url"]) or os.getenv(ENV_VARS["redis_url"]),
            session_id=os.getenv(ENV_VARS["session_id"]),
            user_id=os.getenv(ENV_VARS["user_id"]),
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersistenceConfig":
        """Create config from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})
    
    @classmethod
    def from_yaml(cls, path: str) -> "PersistenceConfig":
        """Load config from YAML file."""
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML required for YAML config. Install with: pip install pyyaml")
        
        with open(path) as f:
            data = yaml.safe_load(f)
        
        # Handle nested persistence config
        if "persistence" in data:
            data = data["persistence"]
        
        return cls.from_dict(data)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "conversation_store": self.conversation_store,
            "conversation_url": self.conversation_url,
            "conversation_options": self.conversation_options,
            "knowledge_store": self.knowledge_store,
            "knowledge_url": self.knowledge_url,
            "knowledge_options": self.knowledge_options,
            "state_store": self.state_store,
            "state_url": self.state_url,
            "state_options": self.state_options,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "auto_create_tables": self.auto_create_tables,
            "lazy_init": self.lazy_init,
        }
    
    def validate(self) -> bool:
        """Validate configuration."""
        valid = True
        
        if self.conversation_store and self.conversation_store not in CONVERSATION_BACKENDS:
            logger.error(f"Invalid conversation_store: {self.conversation_store}. "
                        f"Supported: {CONVERSATION_BACKENDS}")
            valid = False
        
        if self.knowledge_store and self.knowledge_store not in KNOWLEDGE_BACKENDS:
            logger.error(f"Invalid knowledge_store: {self.knowledge_store}. "
                        f"Supported: {KNOWLEDGE_BACKENDS}")
            valid = False
        
        if self.state_store and self.state_store not in STATE_BACKENDS:
            logger.error(f"Invalid state_store: {self.state_store}. "
                        f"Supported: {STATE_BACKENDS}")
            valid = False
        
        return valid


def get_env_var(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable by config key name."""
    env_name = ENV_VARS.get(key, key.upper())
    return os.getenv(env_name, default)


def list_available_backends() -> Dict[str, list]:
    """List all available backends by store type."""
    return {
        "conversation": CONVERSATION_BACKENDS,
        "knowledge": KNOWLEDGE_BACKENDS,
        "state": STATE_BACKENDS,
    }
