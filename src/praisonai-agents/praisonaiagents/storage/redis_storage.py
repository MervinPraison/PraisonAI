"""
Redis storage backend for PraisonAI Agents.

This module provides Redis-based storage implementation with caching capabilities,
pub/sub support, and automatic expiration.
"""

import json
import time
import asyncio
from typing import Any, Dict, List, Optional
from .base import BaseStorage

try:
    import redis.asyncio as aioredis
    from redis.asyncio import Redis
    from redis.exceptions import RedisError, ConnectionError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    aioredis = None
    Redis = None


class RedisStorage(BaseStorage):
    """
    Redis storage backend implementation.
    
    Provides high-performance caching and storage with automatic expiration,
    pub/sub capabilities, and optional compression.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Redis storage.
        
        Args:
            config: Configuration dictionary with keys:
                - host: Redis host (default: "localhost")
                - port: Redis port (default: 6379)
                - password: Redis password (default: None)
                - ssl: Use SSL connection (default: False)
                - db: Redis database number (default: 0)
                - default_ttl: Default TTL in seconds (default: None)
                - key_prefix: Key prefix for namespacing (default: "praisonai:")
                - compression: Compression type ("gzip", "lz4", None) (default: None)
                - max_connections: Max connections in pool (default: 10)
                - retry_on_timeout: Retry on timeout (default: True)
                - socket_timeout: Socket timeout in seconds (default: 5)
                - socket_connect_timeout: Connect timeout in seconds (default: 5)
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis storage requires redis[aio]. "
                "Install with: pip install redis[aio]"
            )
        
        super().__init__(config)
        
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 6379)
        self.password = config.get("password")
        self.ssl = config.get("ssl", False)
        self.db = config.get("db", 0)
        self.default_ttl = config.get("default_ttl")
        self.key_prefix = config.get("key_prefix", "praisonai:")
        self.compression = config.get("compression")
        self.max_connections = config.get("max_connections", 10)
        self.retry_on_timeout = config.get("retry_on_timeout", True)
        self.socket_timeout = config.get("socket_timeout", 5)
        self.socket_connect_timeout = config.get("socket_connect_timeout", 5)
        
        # Initialize compression if specified
        self.compressor = None
        self.decompressor = None
        if self.compression:
            self._init_compression()
        
        # Redis client will be initialized on first use
        self.redis = None
        self._initialized = False
    
    def _init_compression(self):
        """Initialize compression functions."""
        if self.compression == "gzip":
            import gzip
            self.compressor = lambda data: gzip.compress(data.encode('utf-8'))
            self.decompressor = lambda data: gzip.decompress(data).decode('utf-8')
        elif self.compression == "lz4":
            try:
                import lz4.frame
                self.compressor = lambda data: lz4.frame.compress(data.encode('utf-8'))
                self.decompressor = lambda data: lz4.frame.decompress(data).decode('utf-8')
            except ImportError:
                self.logger.warning("lz4 not available, disabling compression")
                self.compression = None
        else:
            self.logger.warning(f"Unknown compression type: {self.compression}")
            self.compression = None
    
    def _compress_data(self, data: str) -> bytes:
        """Compress data if compression is enabled."""
        if self.compression and self.compressor:
            try:
                return self.compressor(data)
            except Exception as e:
                self.logger.error(f"Compression failed: {e}")
        return data.encode('utf-8')
    
    def _decompress_data(self, data: bytes) -> str:
        """Decompress data if compression is enabled."""
        if self.compression and self.decompressor:
            try:
                return self.decompressor(data)
            except Exception as e:
                self.logger.error(f"Decompression failed: {e}")
                return data.decode('utf-8')
        return data.decode('utf-8')
    
    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.key_prefix}{key}"
    
    def _strip_prefix(self, key: str) -> str:
        """Remove prefix from key."""
        if key.startswith(self.key_prefix):
            return key[len(self.key_prefix):]
        return key
    
    async def _ensure_connection(self):
        """Ensure Redis connection is established."""
        if not self._initialized:
            try:
                self.redis = Redis(
                    host=self.host,
                    port=self.port,
                    password=self.password,
                    ssl=self.ssl,
                    db=self.db,
                    max_connections=self.max_connections,
                    retry_on_timeout=self.retry_on_timeout,
                    socket_timeout=self.socket_timeout,
                    socket_connect_timeout=self.socket_connect_timeout,
                    decode_responses=False  # We handle encoding/decoding ourselves
                )
                
                # Test connection
                await self.redis.ping()
                
                self._initialized = True
                self.logger.info(f"Connected to Redis: {self.host}:{self.port}")
                
            except ConnectionError as e:
                self.logger.error(f"Failed to connect to Redis: {e}")
                raise
            except Exception as e:
                self.logger.error(f"Unexpected error connecting to Redis: {e}")
                raise
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        await self._ensure_connection()
        
        try:
            redis_key = self._make_key(key)
            data = await self.redis.get(redis_key)
            
            if data:
                # Decompress and parse
                json_str = self._decompress_data(data)
                return json.loads(json_str)
            return None
        except (RedisError, json.JSONDecodeError) as e:
            self.logger.error(f"Failed to read key {key}: {e}")
            return None
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        await self._ensure_connection()
        
        try:
            # Add timestamps
            record = data.copy()
            record["updated_at"] = time.time()
            if "created_at" not in record:
                record["created_at"] = record["updated_at"]
            
            # Serialize and compress
            json_str = json.dumps(record, ensure_ascii=False)
            compressed_data = self._compress_data(json_str)
            
            redis_key = self._make_key(key)
            
            # Set with optional TTL
            if self.default_ttl:
                await self.redis.setex(redis_key, self.default_ttl, compressed_data)
            else:
                await self.redis.set(redis_key, compressed_data)
            
            return True
        except (RedisError, json.JSONEncodeError) as e:
            self.logger.error(f"Failed to write key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        await self._ensure_connection()
        
        try:
            redis_key = self._make_key(key)
            result = await self.redis.delete(redis_key)
            return result > 0
        except RedisError as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for records matching the query.
        
        Note: Redis doesn't have native search capabilities like MongoDB/PostgreSQL.
        This implementation scans all keys and filters client-side, which may be slow
        for large datasets. Consider using RedisSearch module for production use.
        """
        await self._ensure_connection()
        
        try:
            # Get all keys with our prefix
            pattern = f"{self.key_prefix}*"
            keys = await self.redis.keys(pattern)
            
            if not keys:
                return []
            
            # Get all records
            raw_data = await self.redis.mget(keys)
            results = []
            
            # Process and filter records
            for i, data in enumerate(raw_data):
                if data:
                    try:
                        json_str = self._decompress_data(data)
                        record = json.loads(json_str)
                        record["id"] = self._strip_prefix(keys[i].decode())
                        
                        # Apply filters
                        if self._matches_query(record, query):
                            results.append(record)
                            
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        self.logger.error(f"Failed to decode record: {e}")
                        continue
            
            # Sort by updated_at descending
            results.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            
            # Apply limit
            limit = query.get("limit", 100)
            return results[:limit]
            
        except RedisError as e:
            self.logger.error(f"Failed to search: {e}")
            return []
    
    def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a record matches the search query."""
        # Text search in content
        if "text" in query:
            content = str(record.get("content", "")).lower()
            search_text = query["text"].lower()
            if search_text not in content:
                return False
        
        # Metadata search
        if "metadata" in query:
            record_metadata = record.get("metadata", {})
            for key, value in query["metadata"].items():
                if record_metadata.get(key) != value:
                    return False
        
        # Time range filters
        if "created_after" in query:
            if record.get("created_at", 0) < query["created_after"]:
                return False
        
        if "created_before" in query:
            if record.get("created_at", float('inf')) > query["created_before"]:
                return False
        
        return True
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        await self._ensure_connection()
        
        try:
            # Build pattern
            if prefix:
                pattern = f"{self.key_prefix}{prefix}*"
            else:
                pattern = f"{self.key_prefix}*"
            
            keys = await self.redis.keys(pattern)
            
            # Strip prefix and decode
            stripped_keys = [self._strip_prefix(key.decode()) for key in keys]
            
            # Sort by key name (Redis doesn't maintain insertion order)
            stripped_keys.sort()
            
            if limit:
                stripped_keys = stripped_keys[:limit]
            
            return stripped_keys
        except RedisError as e:
            self.logger.error(f"Failed to list keys: {e}")
            return []
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        await self._ensure_connection()
        
        try:
            # Get all keys with our prefix
            pattern = f"{self.key_prefix}*"
            keys = await self.redis.keys(pattern)
            
            if keys:
                await self.redis.delete(*keys)
            
            return True
        except RedisError as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
    
    async def batch_write(self, records: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Optimized batch write for Redis."""
        await self._ensure_connection()
        
        results = {}
        
        try:
            # Use pipeline for atomic batch operations
            pipe = self.redis.pipeline()
            current_time = time.time()
            
            # Prepare all operations
            for key, data in records.items():
                record = data.copy()
                record["updated_at"] = current_time
                if "created_at" not in record:
                    record["created_at"] = current_time
                
                json_str = json.dumps(record, ensure_ascii=False)
                compressed_data = self._compress_data(json_str)
                redis_key = self._make_key(key)
                
                if self.default_ttl:
                    pipe.setex(redis_key, self.default_ttl, compressed_data)
                else:
                    pipe.set(redis_key, compressed_data)
            
            # Execute pipeline
            await pipe.execute()
            
            # Mark all as successful
            for key in records.keys():
                results[key] = True
                
        except (RedisError, json.JSONEncodeError) as e:
            self.logger.error(f"Failed batch write: {e}")
            for key in records.keys():
                results[key] = False
        
        return results
    
    async def batch_read(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Optimized batch read for Redis."""
        await self._ensure_connection()
        
        results = {key: None for key in keys}
        
        try:
            # Prepare Redis keys
            redis_keys = [self._make_key(key) for key in keys]
            
            # Use mget for batch read
            raw_data = await self.redis.mget(redis_keys)
            
            # Process results
            for i, data in enumerate(raw_data):
                if data:
                    try:
                        json_str = self._decompress_data(data)
                        record = json.loads(json_str)
                        results[keys[i]] = record
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        self.logger.error(f"Failed to decode record for key {keys[i]}: {e}")
                        
        except RedisError as e:
            self.logger.error(f"Failed batch read: {e}")
        
        return results
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        await self._ensure_connection()
        
        try:
            redis_key = self._make_key(key)
            result = await self.redis.exists(redis_key)
            return result > 0
        except RedisError as e:
            self.logger.error(f"Failed to check existence of key {key}: {e}")
            return False
    
    async def count(self) -> int:
        """Count total number of records in storage."""
        await self._ensure_connection()
        
        try:
            pattern = f"{self.key_prefix}*"
            keys = await self.redis.keys(pattern)
            return len(keys)
        except RedisError as e:
            self.logger.error(f"Failed to count records: {e}")
            return 0
    
    async def set_ttl(self, key: str, ttl: int) -> bool:
        """Set TTL for a specific key."""
        await self._ensure_connection()
        
        try:
            redis_key = self._make_key(key)
            result = await self.redis.expire(redis_key, ttl)
            return result
        except RedisError as e:
            self.logger.error(f"Failed to set TTL for key {key}: {e}")
            return False
    
    async def get_ttl(self, key: str) -> Optional[int]:
        """Get TTL for a specific key."""
        await self._ensure_connection()
        
        try:
            redis_key = self._make_key(key)
            ttl = await self.redis.ttl(redis_key)
            return ttl if ttl >= 0 else None
        except RedisError as e:
            self.logger.error(f"Failed to get TTL for key {key}: {e}")
            return None
    
    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            self._initialized = False