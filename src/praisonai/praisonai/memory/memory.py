"""
Memory implementation for PraisonAI (moved from core SDK).

This is the concrete implementation of memory backends including SQLite, 
ChromaDB, MongoDB, and Mem0. This was moved from praisonaiagents to maintain
the protocol-driven architecture where core contains only protocols.
"""

import os
import sqlite3
import json
import time
import shutil
import threading
from typing import Any, Dict, List, Optional, Union, Literal
import logging
from datetime import datetime

# Import protocols from core SDK
try:
    from praisonaiagents.memory.protocols import MemoryProtocol, AgentMemoryProtocol
    from praisonaiagents._lazy import lazy_import
    from praisonaiagents._logging import get_logger
except ImportError:
    # Fallback imports for testing
    from typing import Protocol
    
    class MemoryProtocol(Protocol):
        def store_short_term(self, text: str, metadata=None, **kwargs) -> str: ...
        def search_short_term(self, query: str, limit: int = 5, **kwargs): ...
        def store_long_term(self, text: str, metadata=None, **kwargs) -> str: ...
        def search_long_term(self, query: str, limit: int = 5, **kwargs): ...
        def get_all_memories(self, **kwargs): ...
    
    class AgentMemoryProtocol(Protocol):
        def get_context(self, query=None, **kwargs) -> str: ...
        def save_session(self, name: str, conversation_history=None, metadata=None, **kwargs): ...
    
    def get_logger(name, **kwargs):
        return logging.getLogger(name)
    
    def lazy_import(module, attr):
        import importlib
        return getattr(importlib.import_module(module), attr)

# Import decomposed memory functionality
from .storage import StorageMixin
from .search import SearchMixin
from .core import MemoryCoreMixin

logger = get_logger(__name__, extra_data={"subsystem": "memory"})

# Thread-safe lazy imports using proper thread synchronization
_import_lock = threading.Lock()
_module_cache = {}

def _check_chromadb():
    """Thread-safe lazy check for chromadb availability."""
    if "chromadb" in _module_cache:
        return _module_cache["chromadb"]["available"]
    
    with _import_lock:
        if "chromadb" in _module_cache:
            return _module_cache["chromadb"]["available"]
        
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            _module_cache["chromadb"] = {
                "available": True,
                "module": chromadb,
                "settings": ChromaSettings
            }
        except ImportError:
            _module_cache["chromadb"] = {"available": False}
        
        return _module_cache["chromadb"]["available"]

def _get_chromadb():
    """Get chromadb module and settings (thread-safe lazy load)."""
    if not _check_chromadb():
        raise ImportError("chromadb is required. Install with: pip install chromadb")
    return _module_cache["chromadb"]["module"], _module_cache["chromadb"]["settings"]

def _check_mem0():
    """Thread-safe lazy check for mem0 availability."""
    if "mem0" in _module_cache:
        return _module_cache["mem0"]["available"]
    
    with _import_lock:
        if "mem0" in _module_cache:
            return _module_cache["mem0"]["available"]
        
        try:
            import mem0
            _module_cache["mem0"] = {
                "available": True,
                "module": mem0
            }
        except ImportError:
            _module_cache["mem0"] = {"available": False}
        
        return _module_cache["mem0"]["available"]

def _get_mem0():
    """Get mem0 module (thread-safe lazy load)."""
    if not _check_mem0():
        raise ImportError("mem0 is required. Install with: pip install mem0ai")
    return _module_cache["mem0"]["module"]

def _check_openai():
    """Thread-safe lazy check for openai availability."""
    if "openai" in _module_cache:
        return _module_cache["openai"]["available"]
    
    with _import_lock:
        if "openai" in _module_cache:
            return _module_cache["openai"]["available"]
        
        try:
            from openai import OpenAI
            _module_cache["openai"] = {
                "available": True,
                "client": OpenAI
            }
        except ImportError:
            _module_cache["openai"] = {"available": False}
        
        return _module_cache["openai"]["available"]

def _get_openai():
    """Get OpenAI client (thread-safe lazy load)."""
    if not _check_openai():
        raise ImportError("openai is required. Install with: pip install openai")
    return _module_cache["openai"]["client"]

def _check_pymongo():
    """Thread-safe lazy check for pymongo availability."""
    if "pymongo" in _module_cache:
        return _module_cache["pymongo"]["available"]
    
    with _import_lock:
        if "pymongo" in _module_cache:
            return _module_cache["pymongo"]["available"]
        
        try:
            import pymongo
            from pymongo import MongoClient
            _module_cache["pymongo"] = {
                "available": True,
                "module": pymongo,
                "client": MongoClient
            }
        except ImportError:
            _module_cache["pymongo"] = {"available": False}
        
        return _module_cache["pymongo"]["available"]

def _get_pymongo():
    """Get pymongo module and MongoClient (thread-safe lazy load)."""
    if not _check_pymongo():
        raise ImportError("pymongo is required. Install with: pip install pymongo")
    return _module_cache["pymongo"]["module"], _module_cache["pymongo"]["client"]


class Memory(StorageMixin, SearchMixin, MemoryCoreMixin):
    """
    A single-file memory manager covering:
    - Short-term memory (STM) for ephemeral context
    - Long-term memory (LTM) for persistent knowledge
    - Entity memory (structured data about named entities)
    - User memory (preferences/history for each user)
    - Quality score logic for deciding which data to store in LTM
    - Context building from multiple memory sources
    - Graph memory support for complex relationship storage (via Mem0)

    Config example:
    {
      "provider": "rag" or "mem0" or "mongodb" or "none",
      "use_embedding": True,
      "short_db": "short_term.db",
      "long_db": "long_term.db",
      "rag_db_path": "rag_db",   # optional path for local embedding store
      "config": {
        "api_key": "...",       # if mem0 usage
        "org_id": "...",
        "project_id": "...",    # if mem0 usage
        "vector_store": {       # optional mem0 vector store config
          "provider": "chroma",
          "config": {
            "collection_name": "my_collection",
            "path": "/path/to/chroma"
          }
        }
      },
      "use_long_term": True,    # optionally skip LTM
      "quality_threshold": 7.0  # minimum score for LTM storage
    }
    
    Implements both MemoryProtocol and AgentMemoryProtocol for full compatibility.
    """
    
    def __init__(self, cfg: Dict[str, Any] = None):
        """Initialize memory manager with configuration."""
        self.cfg = cfg or {}
        self.verbose = self.cfg.get("verbose", 0)
        self._local = threading.local()
        self._connection_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._all_connections = set()

        # Determine active provider and feature flags (used by mixin classes)
        self.provider = self.cfg.get("provider", "rag")
        self.use_rag = (
            self.provider.lower() == "rag"
            and _check_chromadb()
            and self.cfg.get("use_embedding", False)
        )
        self.use_mongodb = self.provider.lower() == "mongodb" and _check_pymongo()

        # Learn support
        self._learn_manager = None
        self._learn_config = self.cfg.get("learn", None)

        # Initialize SQLite STM/LTM tables via StorageMixin helpers
        if self.provider != "mem0":
            self._init_stm()
            self._init_ltm()

        # Set up Mem0 client if requested
        self.mem0_client = None
        if self.provider == "mem0":
            self._init_mem0()

        # Set up MongoDB client if requested
        self.mongo_client = None
        self.mongo_db = None
        if self.use_mongodb:
            self._init_mongodb()

        # Set up local vector store if using RAG embeddings
        if self.use_rag:
            self._init_chroma()
    
    def _init_mem0(self):
        """Initialize Mem0 client for graph memory."""
        if not _check_mem0():
            logger.warning("mem0 not available. Install with: pip install mem0ai")
            return
            
        mem0_module = _get_mem0()
        config = self.cfg.get("config", {})
        
        try:
            self.mem0_client = mem0_module.Memory(config=config)
            logger.debug("Initialized Mem0 client")
        except Exception as e:
            logger.error(f"Failed to initialize Mem0 client: {e}")

    def _init_mongodb(self):
        """Initialize MongoDB client."""
        if not _check_pymongo():
            logger.warning("pymongo not available. Install with: pip install pymongo")
            return
        
        pymongo_info = _get_pymongo()
        MongoClient = pymongo_info["MongoClient"]
        mongo_config = self.cfg.get("config", {})
        uri = mongo_config.get("uri", "mongodb://localhost:27017/")
        
        try:
            self.mongo_client = MongoClient(uri)
            db_name = mongo_config.get("database", "praisonai_memory")
            self.mongo_db = self.mongo_client[db_name]
            logger.debug(f"Initialized MongoDB client for database: {db_name}")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB client: {e}")

    def _init_chroma(self):
        """Initialize ChromaDB for local vector storage."""
        if not _check_chromadb():
            logger.warning("chromadb not available. Install with: pip install chromadb")
            return
        
        chromadb_info = _get_chromadb()
        chromadb_module = chromadb_info["module"]
        ChromaSettings = chromadb_info["settings"]
        
        try:
            persist_directory = self.cfg.get("rag_db_path", "./rag_db")
            os.makedirs(persist_directory, exist_ok=True)
            
            settings = ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
                persist_directory=persist_directory
            )
            
            self.chroma_client = chromadb_module.PersistentClient(
                path=persist_directory,
                settings=settings
            )
            
            collection_name = self.cfg.get("collection_name", "memory_collection")
            self.stm_collection = self.chroma_client.get_or_create_collection(
                name=f"{collection_name}_short_term"
            )
            self.ltm_collection = self.chroma_client.get_or_create_collection(
                name=f"{collection_name}_long_term"
            )
            
            logger.debug(f"Initialized ChromaDB collection: {collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")

    def close_connections(self):
        """Close all database connections."""
        # Close thread-local connections
        if hasattr(self._local, 'stm_conn') and self._local.stm_conn:
            try:
                self._local.stm_conn.close()
                self._local.stm_conn = None
            except Exception as e:
                logger.warning(f"Error closing current thread's STM connection: {e}")
        
        if hasattr(self._local, 'ltm_conn') and self._local.ltm_conn:
            try:
                self._local.ltm_conn.close()
                self._local.ltm_conn = None
            except Exception as e:
                logger.warning(f"Error closing current thread's LTM connection: {e}")
        
        # Close all known connections from the registry
        with self._connection_lock:
            connections_to_close = list(self._all_connections)
            for conn in connections_to_close:
                try:
                    conn.close()
                except Exception as e:
                    logger.debug(f"Error closing registered connection: {e}")
            self._all_connections.clear()
    
    def __enter__(self):
        """Allow Memory to be used as a context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure connections are closed when leaving a context manager block."""
        self.close_connections()
    
    def _safe_mem0_search(self, mem0_client, **kwargs):
        """
        Defensive wrapper for mem0.search() to handle MongoDB vector store compatibility.
        
        Catches TypeError about unexpected 'vectors' kwarg and falls back gracefully.
        This addresses the upstream mem0 bug: https://github.com/mem0ai/mem0/issues/3185
        """
        try:
            return mem0_client.search(**kwargs)
        except TypeError as e:
            error_msg = str(e).lower()
            if "unexpected keyword argument" in error_msg and "vectors" in error_msg:
                logger.warning(
                    "Detected mem0 MongoDB vector store compatibility issue. "
                    "This is a known upstream bug: https://github.com/mem0ai/mem0/issues/3185. "
                    "The MongoDB vector store requires Atlas and has signature mismatches. "
                    "Consider using Qdrant or Chroma as mem0 vector store backends instead."
                )
                return []
            else:
                raise

    def __del__(self):
        """
        Attempt to clean up any open SQLite connections when this instance
        is garbage-collected. Errors are suppressed to avoid issues during
        interpreter shutdown.
        """
        try:
            self.close_connections()
        except Exception:
            pass  # Best-effort cleanup during garbage collection