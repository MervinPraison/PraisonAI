"""
Storage module for PraisonAI Agents

This module provides unified storage backend support including:
- MongoDB storage
- PostgreSQL storage  
- DynamoDB storage
- Redis caching/storage
- Cloud storage (S3, GCS, Azure)
- SQLite storage (legacy)
"""

from .base import BaseStorage
from .sqlite_storage import SQLiteStorage

# Optional storage backends that require additional dependencies
try:
    from .mongodb_storage import MongoDBStorage
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    MongoDBStorage = None

try:
    from .postgresql_storage import PostgreSQLStorage
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    PostgreSQLStorage = None

try:
    from .redis_storage import RedisStorage
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    RedisStorage = None

try:
    from .dynamodb_storage import DynamoDBStorage
    DYNAMODB_AVAILABLE = True
except ImportError:
    DYNAMODB_AVAILABLE = False
    DynamoDBStorage = None

try:
    from .cloud_storage import S3Storage, GCSStorage, AzureStorage
    CLOUD_AVAILABLE = True
except ImportError:
    CLOUD_AVAILABLE = False
    S3Storage = None
    GCSStorage = None
    AzureStorage = None

__all__ = [
    "BaseStorage",
    "SQLiteStorage",
    "MongoDBStorage", 
    "PostgreSQLStorage",
    "RedisStorage",
    "DynamoDBStorage",
    "S3Storage",
    "GCSStorage", 
    "AzureStorage"
]