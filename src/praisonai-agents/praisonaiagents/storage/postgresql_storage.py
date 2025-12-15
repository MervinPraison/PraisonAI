"""
PostgreSQL storage backend for PraisonAI Agents.

This module provides PostgreSQL-based storage implementation with full SQL capabilities,
JSONB support, and advanced indexing.
"""

import time
import json
import asyncio
from typing import Any, Dict, List, Optional
from .base import BaseStorage

try:
    import asyncpg
    import asyncpg.pool
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    asyncpg = None


class PostgreSQLStorage(BaseStorage):
    """
    PostgreSQL storage backend implementation.
    
    Provides scalable SQL storage with JSONB support, full-text search,
    and advanced indexing capabilities.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize PostgreSQL storage.
        
        Args:
            config: Configuration dictionary with keys:
                - url: PostgreSQL connection URL (default: "postgresql://localhost/praisonai")
                - schema: Schema name (default: "public")
                - table_prefix: Table name prefix (default: "agent_")
                - table_name: Full table name (overrides prefix, default: None)
                - use_jsonb: Use JSONB for flexible data (default: True)
                - connection_pool_size: Pool size (default: 10)
                - max_connections: Max connections (default: 20)
                - command_timeout: Command timeout in seconds (default: 60)
        """
        if not POSTGRESQL_AVAILABLE:
            raise ImportError(
                "PostgreSQL storage requires asyncpg. "
                "Install with: pip install asyncpg"
            )
        
        super().__init__(config)
        
        self.url = config.get("url", "postgresql://localhost/praisonai")
        self.schema = config.get("schema", "public")
        self.table_prefix = config.get("table_prefix", "agent_")
        self.table_name = config.get("table_name") or f"{self.table_prefix}memory"
        self.use_jsonb = config.get("use_jsonb", True)
        self.pool_size = config.get("connection_pool_size", 10)
        self.max_connections = config.get("max_connections", 20)
        self.command_timeout = config.get("command_timeout", 60)
        
        # Connection pool will be initialized on first use
        self.pool = None
        self._initialized = False
    
    async def _ensure_connection(self):
        """Ensure PostgreSQL connection pool is established."""
        if not self._initialized:
            try:
                self.pool = await asyncpg.create_pool(
                    self.url,
                    min_size=self.pool_size,
                    max_size=self.max_connections,
                    command_timeout=self.command_timeout
                )
                
                # Create schema and table
                await self._create_schema_and_table()
                
                self._initialized = True
                self.logger.info(f"Connected to PostgreSQL: {self.schema}.{self.table_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to connect to PostgreSQL: {e}")
                raise
    
    async def _create_schema_and_table(self):
        """Create schema and table if they don't exist."""
        async with self.pool.acquire() as conn:
            try:
                # Create schema if specified
                if self.schema != "public":
                    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
                
                # Determine column types based on configuration
                if self.use_jsonb:
                    content_type = "JSONB"
                    metadata_type = "JSONB"
                else:
                    content_type = "TEXT"
                    metadata_type = "JSONB"  # Always use JSONB for metadata
                
                # Create table
                await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.schema}.{self.table_name} (
                    id TEXT PRIMARY KEY,
                    content {content_type} NOT NULL,
                    metadata {metadata_type},
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """)
                
                # Create indexes for better performance
                await self._create_indexes(conn)
                
                self.logger.info("PostgreSQL schema and table created successfully")
                
            except Exception as e:
                self.logger.error(f"Failed to create PostgreSQL schema/table: {e}")
                raise
    
    async def _create_indexes(self, conn):
        """Create indexes for better performance."""
        table_ref = f"{self.schema}.{self.table_name}"
        
        try:
            # Basic indexes
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_created_at ON {table_ref} (created_at)")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated_at ON {table_ref} (updated_at)")
            
            # JSONB indexes
            if self.use_jsonb:
                # GIN index on content for full document search
                await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_content_gin ON {table_ref} USING gin (content)")
            else:
                # Text search index on content
                await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_content_text ON {table_ref} USING gin (to_tsvector('english', content))")
            
            # GIN index on metadata
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_metadata_gin ON {table_ref} USING gin (metadata)")
            
        except Exception as e:
            self.logger.error(f"Failed to create PostgreSQL indexes: {e}")
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    f"SELECT id, content, metadata, created_at, updated_at FROM {self.schema}.{self.table_name} WHERE id = $1",
                    key
                )
                
                if row:
                    return {
                        "id": row["id"],
                        "content": row["content"],
                        "metadata": row["metadata"] or {},
                        "created_at": row["created_at"].timestamp(),
                        "updated_at": row["updated_at"].timestamp()
                    }
                return None
            except Exception as e:
                self.logger.error(f"Failed to read key {key}: {e}")
                return None
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                content = data.get("content", "")
                metadata = data.get("metadata", {})
                
                # Handle content based on JSONB setting
                if self.use_jsonb and isinstance(content, str):
                    try:
                        # Try to parse as JSON if it's a string
                        content = json.loads(content)
                    except (json.JSONDecodeError, TypeError):
                        # Keep as string if not valid JSON
                        pass
                
                # Use ON CONFLICT for upsert behavior
                await conn.execute(f"""
                INSERT INTO {self.schema}.{self.table_name} (id, content, metadata, created_at, updated_at)
                VALUES ($1, $2, $3, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """, key, content, metadata)
                
                return True
            except Exception as e:
                self.logger.error(f"Failed to write key {key}: {e}")
                return False
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                result = await conn.execute(
                    f"DELETE FROM {self.schema}.{self.table_name} WHERE id = $1",
                    key
                )
                # Extract affected rows from result string like "DELETE 1"
                affected_rows = int(result.split()[-1]) if result.split() else 0
                return affected_rows > 0
            except Exception as e:
                self.logger.error(f"Failed to delete key {key}: {e}")
                return False
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for records matching the query."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                # Build WHERE clause
                where_conditions = []
                params = []
                param_count = 0
                
                # Text search
                if "text" in query:
                    param_count += 1
                    if self.use_jsonb:
                        # Search in JSONB content
                        where_conditions.append(f"content::text ILIKE ${param_count}")
                        params.append(f"%{query['text']}%")
                    else:
                        # Full-text search
                        where_conditions.append(f"to_tsvector('english', content) @@ plainto_tsquery('english', ${param_count})")
                        params.append(query["text"])
                
                # Metadata search
                if "metadata" in query:
                    for key, value in query["metadata"].items():
                        param_count += 1
                        where_conditions.append(f"metadata ->> ${param_count} = ${param_count + 1}")
                        params.extend([key, str(value)])
                        param_count += 1
                
                # Time range filters
                if "created_after" in query:
                    param_count += 1
                    where_conditions.append(f"created_at >= to_timestamp(${param_count})")
                    params.append(query["created_after"])
                
                if "created_before" in query:
                    param_count += 1
                    where_conditions.append(f"created_at <= to_timestamp(${param_count})")
                    params.append(query["created_before"])
                
                # Build SQL query
                sql = f"SELECT id, content, metadata, created_at, updated_at FROM {self.schema}.{self.table_name}"
                if where_conditions:
                    sql += " WHERE " + " AND ".join(where_conditions)
                
                sql += " ORDER BY updated_at DESC"
                
                # Add limit
                limit = query.get("limit", 100)
                param_count += 1
                sql += f" LIMIT ${param_count}"
                params.append(limit)
                
                rows = await conn.fetch(sql, *params)
                
                results = []
                for row in rows:
                    results.append({
                        "id": row["id"],
                        "content": row["content"],
                        "metadata": row["metadata"] or {},
                        "created_at": row["created_at"].timestamp(),
                        "updated_at": row["updated_at"].timestamp()
                    })
                
                return results
            except Exception as e:
                self.logger.error(f"Failed to search: {e}")
                return []
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                sql = f"SELECT id FROM {self.schema}.{self.table_name}"
                params = []
                
                if prefix:
                    sql += " WHERE id LIKE $1"
                    params.append(f"{prefix}%")
                
                sql += " ORDER BY created_at DESC"
                
                if limit:
                    param_num = len(params) + 1
                    sql += f" LIMIT ${param_num}"
                    params.append(limit)
                
                rows = await conn.fetch(sql, *params)
                return [row["id"] for row in rows]
            except Exception as e:
                self.logger.error(f"Failed to list keys: {e}")
                return []
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(f"DELETE FROM {self.schema}.{self.table_name}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to clear storage: {e}")
                return False
    
    async def batch_write(self, records: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Optimized batch write for PostgreSQL."""
        await self._ensure_connection()
        
        results = {}
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # Prepare batch data
                    batch_data = []
                    for key, data in records.items():
                        content = data.get("content", "")
                        metadata = data.get("metadata", {})
                        
                        # Handle content based on JSONB setting
                        if self.use_jsonb and isinstance(content, str):
                            try:
                                content = json.loads(content)
                            except (json.JSONDecodeError, TypeError):
                                pass
                        
                        batch_data.append((key, content, metadata))
                    
                    # Execute batch upsert
                    await conn.executemany(f"""
                    INSERT INTO {self.schema}.{self.table_name} (id, content, metadata, created_at, updated_at)
                    VALUES ($1, $2, $3, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    """, batch_data)
                    
                    # Mark all as successful
                    for key in records.keys():
                        results[key] = True
                        
                except Exception as e:
                    self.logger.error(f"Failed batch write: {e}")
                    for key in records.keys():
                        results[key] = False
        
        return results
    
    async def batch_read(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Optimized batch read for PostgreSQL."""
        await self._ensure_connection()
        
        results = {key: None for key in keys}
        
        async with self.pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    f"SELECT id, content, metadata, created_at, updated_at FROM {self.schema}.{self.table_name} WHERE id = ANY($1)",
                    keys
                )
                
                for row in rows:
                    results[row["id"]] = {
                        "id": row["id"],
                        "content": row["content"],
                        "metadata": row["metadata"] or {},
                        "created_at": row["created_at"].timestamp(),
                        "updated_at": row["updated_at"].timestamp()
                    }
                    
            except Exception as e:
                self.logger.error(f"Failed batch read: {e}")
        
        return results
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists in storage."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchval(
                    f"SELECT 1 FROM {self.schema}.{self.table_name} WHERE id = $1 LIMIT 1",
                    key
                )
                return result is not None
            except Exception as e:
                self.logger.error(f"Failed to check existence of key {key}: {e}")
                return False
    
    async def count(self) -> int:
        """Count total number of records in storage."""
        await self._ensure_connection()
        
        async with self.pool.acquire() as conn:
            try:
                return await conn.fetchval(f"SELECT COUNT(*) FROM {self.schema}.{self.table_name}")
            except Exception as e:
                self.logger.error(f"Failed to count records: {e}")
                return 0
    
    async def close(self):
        """Close PostgreSQL connection pool."""
        if self.pool:
            await self.pool.close()
            self._initialized = False