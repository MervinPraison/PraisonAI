"""
Storage adapter implementations for PraisonAI.

Heavy implementations that follow StorageBackendProtocol for:
- Redis (praisonai[redis])
- MongoDB (praisonai[mongodb])
- PostgreSQL (praisonai[postgresql])
- DynamoDB (praisonai[dynamodb])
- Valkey (praisonai[valkey])

NOTE: ``praisonai.storage`` is a legacy parallel stack. The active persistence
layer is ``praisonai.persistence``. New code should use ``create_state_store``,
``create_conversation_store``, or ``create_knowledge_store`` from
``praisonai.persistence.factory``.
"""

# Lazy imports - only import when needed
__all__ = [
    "RedisStorageAdapter",
    "MongoDBStorageAdapter",
    "PostgreSQLStorageAdapter",
    "DynamoDBStorageAdapter",
    "ValkeyStorageAdapter",
    "ValkeySearchBackend",
    "ValkeyBackend",
]

# NOTE: To maintain backward compatibility with existing code that uses
# ``from praisonai.storage import XxxStorageAdapter``, the lazy loader below
# keeps the original file-based class definitions accessible. These are NOT
# thin shims — the originals remain the canonical definition until eliminated.


def __getattr__(name: str):
    """Lazy import storage adapters."""
    if name == "RedisStorageAdapter":
        from .redis_adapter import RedisStorageAdapter
        return RedisStorageAdapter
    elif name == "MongoDBStorageAdapter":
        from .mongodb_adapter import MongoDBStorageAdapter
        return MongoDBStorageAdapter
    elif name == "PostgreSQLStorageAdapter":
        from .postgresql_adapter import PostgreSQLStorageAdapter
        return PostgreSQLStorageAdapter
    elif name == "DynamoDBStorageAdapter":
        from .dynamodb_adapter import DynamoDBStorageAdapter
        return DynamoDBStorageAdapter
    elif name == "ValkeyStorageAdapter":
        from .valkey_adapter import ValkeyStorageAdapter
        return ValkeyStorageAdapter
    elif name == "ValkeySearchBackend":
        from .valkey_adapter import ValkeySearchBackend
        return ValkeySearchBackend
    elif name == "ValkeyBackend":
        cls = _make_valkey_backend_class()
        globals()["ValkeyBackend"] = cls
        return cls
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def _make_valkey_backend_class():
    """Return ValkeyBackend — ValkeyStorageAdapter pre-configured from env vars."""
    import os
    from .valkey_adapter import ValkeyStorageAdapter

    class ValkeyBackend(ValkeyStorageAdapter):
        def __init__(
            self,
            host: str = None,
            port: int = None,
            prefix: str = None,
            ttl=None,
            password: str = None,
        ):
            super().__init__(
                host=host if host is not None else os.environ.get("VALKEY_HOST", "localhost"),
                port=int(port if port is not None else os.environ.get("VALKEY_PORT", 6379)),
                prefix=prefix if prefix is not None else os.environ.get("VALKEY_PREFIX", "praisonai:"),
                ttl=ttl,
                password=password if password is not None else os.environ.get("VALKEY_PASSWORD"),
            )

    return ValkeyBackend
