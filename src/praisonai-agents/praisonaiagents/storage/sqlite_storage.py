"""
SQLite storage backend for PraisonAI Agents.

This module provides SQLite-based storage implementation that is compatible
with the existing memory system while providing the new unified interface.
"""

import os
import sqlite3
import json
import time
import asyncio
from typing import Any, Dict, List, Optional
from .base import BaseStorage


class SQLiteStorage(BaseStorage):
    """
    SQLite storage backend implementation.
    
    Provides persistent storage using SQLite database with JSON metadata support.
    Compatible with existing memory system database structure.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize SQLite storage.
        
        Args:
            config: Configuration dictionary with keys:
                - db_path: Path to SQLite database file (default: ".praison/storage.db")
                - table_name: Name of the table (default: "memory_storage") 
                - auto_vacuum: Enable auto vacuum (default: True)
        """
        super().__init__(config)
        
        self.db_path = config.get("db_path", ".praison/storage.db")
        self.table_name = config.get("table_name", "memory_storage")
        self.auto_vacuum = config.get("auto_vacuum", True)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        # Initialize database
        asyncio.create_task(self._init_db()) if asyncio.get_event_loop().is_running() else self._init_db_sync()
    
    def _init_db_sync(self):
        """Initialize database synchronously."""
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            
            # Create table with optimized schema
            c.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """)
            
            # Create indexes for better performance
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_created_at ON {self.table_name}(created_at)")
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{self.table_name}_updated_at ON {self.table_name}(updated_at)")
            
            # Enable auto vacuum if configured
            if self.auto_vacuum:
                c.execute("PRAGMA auto_vacuum = FULL")
            
            conn.commit()
        finally:
            conn.close()
    
    async def _init_db(self):
        """Initialize database asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._init_db_sync)
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with optimizations."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        conn.execute("PRAGMA synchronous=NORMAL")  # Better performance
        conn.execute("PRAGMA cache_size=10000")  # Larger cache
        return conn
    
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """Read a record by key."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._read_sync, key)
    
    def _read_sync(self, key: str) -> Optional[Dict[str, Any]]:
        """Synchronous read implementation."""
        conn = self._get_connection()
        try:
            c = conn.cursor()
            row = c.execute(
                f"SELECT content, metadata, created_at, updated_at FROM {self.table_name} WHERE id = ?",
                (key,)
            ).fetchone()
            
            if row:
                content, metadata_str, created_at, updated_at = row
                metadata = json.loads(metadata_str) if metadata_str else {}
                return {
                    "id": key,
                    "content": content,
                    "metadata": metadata,
                    "created_at": created_at,
                    "updated_at": updated_at
                }
            return None
        finally:
            conn.close()
    
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """Write a record."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._write_sync, key, data)
    
    def _write_sync(self, key: str, data: Dict[str, Any]) -> bool:
        """Synchronous write implementation."""
        conn = self._get_connection()
        try:
            c = conn.cursor()
            
            content = data.get("content", "")
            metadata = data.get("metadata", {})
            created_at = data.get("created_at", time.time())
            updated_at = time.time()
            
            # Use INSERT OR REPLACE for upsert behavior
            c.execute(f"""
            INSERT OR REPLACE INTO {self.table_name} 
            (id, content, metadata, created_at, updated_at) 
            VALUES (?, ?, ?, ?, ?)
            """, (
                key,
                content,
                json.dumps(metadata),
                created_at,
                updated_at
            ))
            
            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"Failed to write key {key}: {e}")
            return False
        finally:
            conn.close()
    
    async def delete(self, key: str) -> bool:
        """Delete a record by key."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._delete_sync, key)
    
    def _delete_sync(self, key: str) -> bool:
        """Synchronous delete implementation."""
        conn = self._get_connection()
        try:
            c = conn.cursor()
            c.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (key,))
            conn.commit()
            return c.rowcount > 0
        except Exception as e:
            self.logger.error(f"Failed to delete key {key}: {e}")
            return False
        finally:
            conn.close()
    
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search for records matching the query."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query)
    
    def _search_sync(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Synchronous search implementation."""
        conn = self._get_connection()
        try:
            c = conn.cursor()
            
            # Build WHERE clause from query
            where_conditions = []
            params = []
            
            # Text search in content
            if "text" in query:
                where_conditions.append("content LIKE ?")
                params.append(f"%{query['text']}%")
            
            # Metadata search (basic JSON text search)
            if "metadata" in query:
                for key, value in query["metadata"].items():
                    where_conditions.append("metadata LIKE ?")
                    params.append(f'%"{key}": "{value}"%')
            
            # Time range filters
            if "created_after" in query:
                where_conditions.append("created_at >= ?")
                params.append(query["created_after"])
            
            if "created_before" in query:
                where_conditions.append("created_at <= ?")
                params.append(query["created_before"])
            
            # Build SQL query
            sql = f"SELECT id, content, metadata, created_at, updated_at FROM {self.table_name}"
            if where_conditions:
                sql += " WHERE " + " AND ".join(where_conditions)
            
            # Add ordering and limit
            sql += " ORDER BY updated_at DESC"
            limit = query.get("limit", 100)
            sql += f" LIMIT {limit}"
            
            rows = c.execute(sql, params).fetchall()
            
            results = []
            for row in rows:
                id_, content, metadata_str, created_at, updated_at = row
                metadata = json.loads(metadata_str) if metadata_str else {}
                results.append({
                    "id": id_,
                    "content": content,
                    "metadata": metadata,
                    "created_at": created_at,
                    "updated_at": updated_at
                })
            
            return results
        except Exception as e:
            self.logger.error(f"Failed to search: {e}")
            return []
        finally:
            conn.close()
    
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """List keys in storage."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_keys_sync, prefix, limit)
    
    def _list_keys_sync(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """Synchronous list_keys implementation."""
        conn = self._get_connection()
        try:
            c = conn.cursor()
            
            sql = f"SELECT id FROM {self.table_name}"
            params = []
            
            if prefix:
                sql += " WHERE id LIKE ?"
                params.append(f"{prefix}%")
            
            sql += " ORDER BY created_at DESC"
            
            if limit:
                sql += f" LIMIT {limit}"
            
            rows = c.execute(sql, params).fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to list keys: {e}")
            return []
        finally:
            conn.close()
    
    async def clear(self) -> bool:
        """Clear all records from storage."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._clear_sync)
    
    def _clear_sync(self) -> bool:
        """Synchronous clear implementation."""
        conn = self._get_connection()
        try:
            c = conn.cursor()
            c.execute(f"DELETE FROM {self.table_name}")
            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
        finally:
            conn.close()
    
    async def batch_write(self, records: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Optimized batch write for SQLite."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._batch_write_sync, records)
    
    def _batch_write_sync(self, records: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """Synchronous batch write implementation."""
        conn = self._get_connection()
        results = {}
        
        try:
            c = conn.cursor()
            
            # Prepare batch data
            batch_data = []
            for key, data in records.items():
                content = data.get("content", "")
                metadata = data.get("metadata", {})
                created_at = data.get("created_at", time.time())
                updated_at = time.time()
                
                batch_data.append((
                    key,
                    content,
                    json.dumps(metadata),
                    created_at,
                    updated_at
                ))
            
            # Execute batch insert
            c.executemany(f"""
            INSERT OR REPLACE INTO {self.table_name}
            (id, content, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """, batch_data)
            
            conn.commit()
            
            # Mark all as successful
            for key in records.keys():
                results[key] = True
                
        except Exception as e:
            self.logger.error(f"Failed batch write: {e}")
            for key in records.keys():
                results[key] = False
        finally:
            conn.close()
        
        return results