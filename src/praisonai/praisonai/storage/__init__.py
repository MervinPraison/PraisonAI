"""
Storage adapter implementations for PraisonAI.

Heavy implementations that follow StorageBackendProtocol for:
- Redis (praisonai[redis])
- MongoDB (praisonai[mongodb])
- PostgreSQL (praisonai[postgresql])
- DynamoDB (praisonai[dynamodb])

These implementations are kept in the wrapper to avoid bloating the core SDK.
"""

# Lazy imports - only import when needed
__all__ = [
    "RedisStorageAdapter",
    "MongoDBStorageAdapter", 
    "PostgreSQLStorageAdapter",
    "DynamoDBStorageAdapter",
]

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
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")