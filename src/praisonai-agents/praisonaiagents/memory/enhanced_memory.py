"""
Enhanced Memory class with unified storage backend support.

This module provides backward-compatible enhancements to the existing Memory class,
adding support for multiple storage backends while maintaining the same interface.
"""

import os
import sqlite3
import json
import time
import asyncio
from typing import Any, Dict, List, Optional, Union, Literal
import logging

# Disable litellm telemetry before any imports
os.environ["LITELLM_TELEMETRY"] = "False"

# Set up logger
logger = logging.getLogger(__name__)

# Import storage backends
try:
    from ..storage import (
        BaseStorage, SQLiteStorage, MongoDBStorage, PostgreSQLStorage,
        RedisStorage, DynamoDBStorage, S3Storage, GCSStorage, AzureStorage
    )
    STORAGE_AVAILABLE = True
except ImportError:
    STORAGE_AVAILABLE = False

# Legacy providers
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    import mem0
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import litellm
    litellm.telemetry = False  # Disable telemetry
    LITELLM_AVAILABLE = True
except ImportError:
    LITELLM_AVAILABLE = False


class EnhancedMemory:
    """
    Enhanced memory manager with unified storage backend support.
    
    Supports all existing providers plus new storage backends:
    - Legacy: "rag" (ChromaDB), "mem0", "none"
    - New: "mongodb", "postgresql", "redis", "dynamodb", "s3", "gcs", "azure", "sqlite"
    
    Config example:
    {
      "provider": "mongodb",  # or any supported provider
      "config": {
        "url": "mongodb://localhost:27017/",
        "database": "praisonai",
        "collection": "agent_memory"
      },
      "cache": {
        "provider": "redis",
        "config": {
          "host": "localhost",
          "port": 6379,
          "default_ttl": 300
        }
      }
    }
    """
    
    def __init__(self, config: Dict[str, Any] = None, verbose: int = 0):
        """
        Initialize enhanced memory with storage backend support.
        
        Args:
            config: Configuration dictionary
            verbose: Verbosity level (0-10)
        """
        self.cfg = config or {}
        self.verbose = verbose
        
        # Set logger level based on verbose
        if verbose >= 5:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)
        
        # Also set other loggers to WARNING
        logging.getLogger('chromadb').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        
        # Initialize storage backends
        self.primary_storage = None
        self.cache_storage = None
        self.legacy_storage = None  # For backward compatibility
        
        # Initialize providers
        self._init_storage_backends()
        
        # Legacy compatibility flags
        self.provider = self.cfg.get("provider", "sqlite")
        self.use_mem0 = False
        self.use_rag = False
        self.graph_enabled = False
        
        # Set up legacy compatibility
        self._setup_legacy_compatibility()
    
    def _init_storage_backends(self):
        """Initialize storage backends based on configuration."""
        if not STORAGE_AVAILABLE:
            logger.warning("Storage backends not available, falling back to legacy mode")
            return
        
        # Initialize primary storage
        provider = self.cfg.get("provider", "sqlite")
        provider_config = self.cfg.get("config", {})
        
        try:
            self.primary_storage = self._create_storage_backend(provider, provider_config)
            self._log_verbose(f"Initialized primary storage: {provider}")
        except Exception as e:
            logger.error(f"Failed to initialize primary storage {provider}: {e}")
            # Fallback to SQLite
            self.primary_storage = self._create_storage_backend("sqlite", {})
        
        # Initialize cache storage if configured
        cache_config = self.cfg.get("cache", {})
        if cache_config:
            cache_provider = cache_config.get("provider", "redis")
            cache_provider_config = cache_config.get("config", {})
            
            try:
                self.cache_storage = self._create_storage_backend(cache_provider, cache_provider_config)
                self._log_verbose(f"Initialized cache storage: {cache_provider}")
            except Exception as e:
                logger.warning(f"Failed to initialize cache storage {cache_provider}: {e}")
    
    def _create_storage_backend(self, provider: str, config: Dict[str, Any]) -> BaseStorage:
        """Create a storage backend instance."""
        provider_lower = provider.lower()
        
        if provider_lower == "sqlite":
            return SQLiteStorage(config)
        elif provider_lower == "mongodb":
            return MongoDBStorage(config)
        elif provider_lower == "postgresql":
            return PostgreSQLStorage(config)
        elif provider_lower == "redis":
            return RedisStorage(config)
        elif provider_lower == "dynamodb":
            return DynamoDBStorage(config)
        elif provider_lower == "s3":
            return S3Storage(config)
        elif provider_lower == "gcs":
            return GCSStorage(config)
        elif provider_lower == "azure":
            return AzureStorage(config)
        else:
            raise ValueError(f"Unsupported storage provider: {provider}")
    
    def _setup_legacy_compatibility(self):
        """Set up legacy compatibility for existing code."""
        provider = self.cfg.get("provider", "sqlite")
        
        if provider.lower() == "mem0" and MEM0_AVAILABLE:
            self.use_mem0 = True
            self._init_mem0()
        elif provider.lower() == "rag" and CHROMADB_AVAILABLE:
            self.use_rag = True
            self._init_chroma()
        elif provider.lower() in ["sqlite", "none"]:
            # Initialize legacy SQLite databases for backward compatibility
            self._init_legacy_sqlite()
    
    def _init_legacy_sqlite(self):
        """Initialize legacy SQLite databases for backward compatibility."""
        # Create .praison directory if it doesn't exist
        os.makedirs(".praison", exist_ok=True)
        
        # Short-term DB
        self.short_db = self.cfg.get("short_db", ".praison/short_term.db")
        self._init_stm()
        
        # Long-term DB
        self.long_db = self.cfg.get("long_db", ".praison/long_term.db")
        self._init_ltm()
    
    def _init_stm(self):
        """Creates or verifies short-term memory table (legacy)."""
        os.makedirs(os.path.dirname(self.short_db) or ".", exist_ok=True)
        conn = sqlite3.connect(self.short_db)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS short_mem (
            id TEXT PRIMARY KEY,
            content TEXT,
            meta TEXT,
            created_at REAL
        )
        """)
        conn.commit()
        conn.close()
    
    def _init_ltm(self):
        """Creates or verifies long-term memory table (legacy)."""
        os.makedirs(os.path.dirname(self.long_db) or ".", exist_ok=True)
        conn = sqlite3.connect(self.long_db)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS long_mem (
            id TEXT PRIMARY KEY,
            content TEXT,
            meta TEXT,
            created_at REAL
        )
        """)
        conn.commit()
        conn.close()
    
    def _init_mem0(self):
        """Initialize Mem0 client (legacy)."""
        # Implementation copied from original memory.py
        mem_cfg = self.cfg.get("config", {})
        api_key = mem_cfg.get("api_key", os.getenv("MEM0_API_KEY"))
        org_id = mem_cfg.get("org_id")
        proj_id = mem_cfg.get("project_id")
        
        # Check if graph memory is enabled
        graph_config = mem_cfg.get("graph_store")
        use_graph = graph_config is not None
        
        if use_graph:
            from mem0 import Memory
            self._log_verbose("Initializing Mem0 with graph memory support")
            
            mem0_config = {}
            mem0_config["graph_store"] = graph_config
            
            if "vector_store" in mem_cfg:
                mem0_config["vector_store"] = mem_cfg["vector_store"]
            if "llm" in mem_cfg:
                mem0_config["llm"] = mem_cfg["llm"]
            if "embedder" in mem_cfg:
                mem0_config["embedder"] = mem_cfg["embedder"]
            
            self.mem0_client = Memory.from_config(config_dict=mem0_config)
            self.graph_enabled = True
        else:
            from mem0 import MemoryClient
            if org_id and proj_id:
                self.mem0_client = MemoryClient(api_key=api_key, org_id=org_id, project_id=proj_id)
            else:
                self.mem0_client = MemoryClient(api_key=api_key)
    
    def _init_chroma(self):
        """Initialize ChromaDB client (legacy)."""
        # Implementation copied from original memory.py
        try:
            rag_path = self.cfg.get("rag_db_path", "chroma_db")
            os.makedirs(rag_path, exist_ok=True)
            
            self.chroma_client = chromadb.PersistentClient(
                path=rag_path,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            collection_name = "memory_store"
            try:
                self.chroma_col = self.chroma_client.get_collection(name=collection_name)
            except Exception:
                self.chroma_col = self.chroma_client.create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
        except Exception as e:
            self._log_verbose(f"Failed to initialize ChromaDB: {e}", logging.ERROR)
            self.use_rag = False
    
    def _log_verbose(self, msg: str, level: int = logging.INFO):
        """Only log if verbose >= 5"""
        if self.verbose >= 5:
            logger.log(level, msg)
    
    # -------------------------------------------------------------------------
    #                      New Unified Storage Methods
    # -------------------------------------------------------------------------
    
    async def store(self, key: str, data: Dict[str, Any], use_cache: bool = True) -> bool:
        """
        Store data in primary storage and optionally cache.
        
        Args:
            key: Unique identifier for the record
            data: Data to store
            use_cache: Whether to also store in cache
            
        Returns:
            True if successful, False otherwise
        """
        if not self.primary_storage:
            return self._legacy_store(key, data)
        
        try:
            # Store in primary storage
            success = await self.primary_storage.write(key, data)
            
            # Store in cache if available and requested
            if success and use_cache and self.cache_storage:
                await self.cache_storage.write(key, data)
            
            return success
        except Exception as e:
            logger.error(f"Failed to store key {key}: {e}")
            return False
    
    async def retrieve(self, key: str, check_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Retrieve data by key, checking cache first if available.
        
        Args:
            key: Unique identifier for the record
            check_cache: Whether to check cache first
            
        Returns:
            Record data or None if not found
        """
        if not self.primary_storage:
            return self._legacy_retrieve(key)
        
        try:
            # Check cache first if available
            if check_cache and self.cache_storage:
                result = await self.cache_storage.read(key)
                if result:
                    return result
            
            # Fallback to primary storage
            result = await self.primary_storage.read(key)
            
            # Store in cache if found and cache is available
            if result and self.cache_storage and check_cache:
                await self.cache_storage.write(key, result)
            
            return result
        except Exception as e:
            logger.error(f"Failed to retrieve key {key}: {e}")
            return None
    
    async def search_unified(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search across storage backends.
        
        Args:
            query: Search query dictionary
            
        Returns:
            List of matching records
        """
        if not self.primary_storage:
            return self._legacy_search(query)
        
        try:
            return await self.primary_storage.search(query)
        except Exception as e:
            logger.error(f"Failed to search: {e}")
            return []
    
    async def delete_unified(self, key: str) -> bool:
        """
        Delete from all storage backends.
        
        Args:
            key: Unique identifier for the record
            
        Returns:
            True if successful, False otherwise
        """
        if not self.primary_storage:
            return self._legacy_delete(key)
        
        try:
            # Delete from primary storage
            success = await self.primary_storage.delete(key)
            
            # Delete from cache if available
            if self.cache_storage:
                await self.cache_storage.delete(key)
            
            return success
        except Exception as e:
            logger.error(f"Failed to delete key {key}: {e}")
            return False
    
    # -------------------------------------------------------------------------
    #                Legacy Compatibility Methods (Synchronous)
    # -------------------------------------------------------------------------
    
    def _legacy_store(self, key: str, data: Dict[str, Any]) -> bool:
        """Legacy store implementation for backward compatibility."""
        try:
            if hasattr(self, 'short_db'):
                conn = sqlite3.connect(self.short_db)
                conn.execute(
                    "INSERT OR REPLACE INTO short_mem (id, content, meta, created_at) VALUES (?,?,?,?)",
                    (key, data.get("content", ""), json.dumps(data.get("metadata", {})), time.time())
                )
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.error(f"Legacy store failed for key {key}: {e}")
        return False
    
    def _legacy_retrieve(self, key: str) -> Optional[Dict[str, Any]]:
        """Legacy retrieve implementation for backward compatibility."""
        try:
            if hasattr(self, 'short_db'):
                conn = sqlite3.connect(self.short_db)
                row = conn.execute(
                    "SELECT content, meta, created_at FROM short_mem WHERE id = ?",
                    (key,)
                ).fetchone()
                conn.close()
                
                if row:
                    return {
                        "id": key,
                        "content": row[0],
                        "metadata": json.loads(row[1] or "{}"),
                        "created_at": row[2]
                    }
        except Exception as e:
            logger.error(f"Legacy retrieve failed for key {key}: {e}")
        return None
    
    def _legacy_search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Legacy search implementation for backward compatibility."""
        try:
            if hasattr(self, 'short_db'):
                conn = sqlite3.connect(self.short_db)
                text_query = query.get("text", "")
                rows = conn.execute(
                    "SELECT id, content, meta, created_at FROM short_mem WHERE content LIKE ? LIMIT ?",
                    (f"%{text_query}%", query.get("limit", 100))
                ).fetchall()
                conn.close()
                
                results = []
                for row in rows:
                    results.append({
                        "id": row[0],
                        "content": row[1],
                        "metadata": json.loads(row[2] or "{}"),
                        "created_at": row[3]
                    })
                return results
        except Exception as e:
            logger.error(f"Legacy search failed: {e}")
        return []
    
    def _legacy_delete(self, key: str) -> bool:
        """Legacy delete implementation for backward compatibility."""
        try:
            if hasattr(self, 'short_db'):
                conn = sqlite3.connect(self.short_db)
                conn.execute("DELETE FROM short_mem WHERE id = ?", (key,))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.error(f"Legacy delete failed for key {key}: {e}")
        return False
    
    # -------------------------------------------------------------------------
    #            Wrapper Methods for Backward Compatibility
    # -------------------------------------------------------------------------
    
    def store_short_term(self, text: str, metadata: Dict[str, Any] = None, **kwargs):
        """Store in short-term memory (legacy compatibility)."""
        key = str(time.time_ns())
        data = {
            "content": text,
            "metadata": metadata or {},
            "created_at": time.time()
        }
        
        if self.primary_storage:
            # Use async storage
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.store(key, data))
            finally:
                loop.close()
        else:
            return self._legacy_store(key, data)
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search short-term memory (legacy compatibility)."""
        search_query = {"text": query, "limit": limit}
        
        if self.primary_storage:
            # Use async storage
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.search_unified(search_query))
            finally:
                loop.close()
        else:
            return self._legacy_search(search_query)
    
    def store_long_term(self, text: str, metadata: Dict[str, Any] = None, **kwargs):
        """Store in long-term memory (legacy compatibility)."""
        return self.store_short_term(text, metadata, **kwargs)
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search long-term memory (legacy compatibility)."""
        return self.search_short_term(query, limit, **kwargs)
    
    # Additional legacy methods for full compatibility
    def store_entity(self, name: str, type_: str, desc: str, relations: str):
        """Store entity info (legacy compatibility)."""
        data = f"Entity {name}({type_}): {desc} | relationships: {relations}"
        return self.store_short_term(data, metadata={"category": "entity"})
    
    def search_entity(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search entity memory (legacy compatibility)."""
        results = self.search_short_term(query, limit=20)
        return [r for r in results if r.get("metadata", {}).get("category") == "entity"][:limit]
    
    def store_user_memory(self, user_id: str, text: str, extra: Dict[str, Any] = None):
        """Store user memory (legacy compatibility)."""
        metadata = {"user_id": user_id}
        if extra:
            metadata.update(extra)
        return self.store_short_term(text, metadata=metadata)
    
    def search_user_memory(self, user_id: str, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search user memory (legacy compatibility)."""
        results = self.search_short_term(query, limit=20)
        return [r for r in results if r.get("metadata", {}).get("user_id") == user_id][:limit]
    
    def search(self, query: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, 
               run_id: Optional[str] = None, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Generic search method (legacy compatibility)."""
        if user_id:
            return self.search_user_memory(user_id, query, limit=limit, **kwargs)
        else:
            return self.search_short_term(query, limit=limit, **kwargs)
    
    # Quality and context methods (simplified for backward compatibility)
    def compute_quality_score(self, completeness: float, relevance: float, 
                            clarity: float, accuracy: float, weights: Dict[str, float] = None) -> float:
        """Compute quality score (legacy compatibility)."""
        if not weights:
            weights = {"completeness": 0.25, "relevance": 0.25, "clarity": 0.25, "accuracy": 0.25}
        total = (completeness * weights["completeness"] + relevance * weights["relevance"] +
                clarity * weights["clarity"] + accuracy * weights["accuracy"])
        return round(total, 3)
    
    def build_context_for_task(self, task_descr: str, user_id: Optional[str] = None, 
                             additional: str = "", max_items: int = 3) -> str:
        """Build context for task (legacy compatibility)."""
        query = (task_descr + " " + additional).strip()
        results = self.search(query, user_id=user_id, limit=max_items)
        
        if not results:
            return ""
        
        lines = ["Memory Context:", "=" * 15]
        for result in results:
            content = result.get("content", "")
            if len(content) > 150:
                content = content[:147] + "..."
            lines.append(f" • {content}")
        
        return "\n".join(lines)
    
    # Reset methods
    def reset_short_term(self):
        """Reset short-term memory (legacy compatibility)."""
        if self.primary_storage:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.primary_storage.clear())
            finally:
                loop.close()
        elif hasattr(self, 'short_db'):
            conn = sqlite3.connect(self.short_db)
            conn.execute("DELETE FROM short_mem")
            conn.commit()
            conn.close()
    
    def reset_long_term(self):
        """Reset long-term memory (legacy compatibility)."""
        return self.reset_short_term()
    
    def reset_all(self):
        """Reset all memory (legacy compatibility)."""
        self.reset_short_term()
        if self.cache_storage:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.cache_storage.clear())
            finally:
                loop.close()


# Factory function for backward compatibility
def Memory(config: Dict[str, Any] = None, verbose: int = 0):
    """
    Factory function to create Memory instance with backward compatibility.
    
    If new storage backends are available, returns EnhancedMemory.
    Otherwise, falls back to original Memory class.
    """
    if STORAGE_AVAILABLE:
        return EnhancedMemory(config, verbose)
    else:
        # Import and return original Memory class
        from .memory import Memory as OriginalMemory
        return OriginalMemory(config, verbose)