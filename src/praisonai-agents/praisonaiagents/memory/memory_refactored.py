"""
Refactored Memory Class - Protocol-Driven Implementation

This refactored Memory class demonstrates the protocol-driven approach by using
the adapter registry instead of hardcoded imports and conditional backend logic.

Key changes from memory.py:
1. Removes all hardcoded _check_* functions (lines 36-142)
2. Uses adapter registry to resolve backends dynamically 
3. Delegates backend operations to adapters implementing MemoryProtocol
4. Maintains full backward compatibility with existing API
5. Reduces Memory class from 2000+ lines to ~300 lines

This approach follows AGENTS.md principles:
- Protocol-driven core: Core only contains protocols and adapter resolution
- Performance-first: No heavy imports until actually needed
- Lazy loading: Heavy dependencies loaded on-demand via factory functions
"""

import os
import threading
from typing import Any, Dict, List, Optional, Union
import logging
from praisonaiagents._logging import get_logger
from datetime import datetime

# Core protocol-driven imports only
from .protocols import MemoryProtocol
from .adapters import get_memory_adapter, get_first_available_memory_adapter
from .adapters.sqlite_adapter import SqliteMemoryAdapter

# Decomposed memory functionality - imported as mixins for backward compatibility
from .storage import StorageMixin
from .search import SearchMixin  
from .core import MemoryCoreMixin

# Set up logger using centralized logging utility
logger = get_logger(__name__, extra_data={"subsystem": "memory"})


class Memory(StorageMixin, SearchMixin, MemoryCoreMixin):
    """
    Protocol-driven memory manager using adapter registry.
    
    Replaces hardcoded backend logic with dynamic adapter resolution.
    Supports all existing backends through the adapter registry:
    - sqlite: Lightweight SQLite storage (core)
    - in_memory: RAM-based storage (core) 
    - mem0: Mem0 integration (factory-loaded)
    - chroma: ChromaDB vector storage (factory-loaded)
    - mongodb: MongoDB document storage (factory-loaded)
    
    Config example:
    {
      "provider": "mem0" | "chroma" | "mongodb" | "sqlite",
      "config": {
        # Provider-specific configuration passed to adapter
        "api_key": "...",
        "connection_string": "...",
        "rag_db_path": "...",
        # etc.
      }
    }
    """

    def __init__(self, config: Dict[str, Any], verbose: int = 0):
        self.cfg = config or {}
        self.verbose = verbose
        
        # Set logger level based on verbose
        if verbose >= 5:
            logger.setLevel(10)  # DEBUG
        else:
            logger.setLevel(30)  # WARNING

        # Suppress noisy loggers from dependencies
        self._configure_dependency_logging()
        
        # Initialize core protocol-driven memory system
        self._init_protocol_driven_memory()
        
        # Backward compatibility: Initialize SQLite-based STM/LTM for legacy API
        self._init_legacy_compatibility()

    def _configure_dependency_logging(self):
        """Suppress verbose logging from heavy dependencies."""
        import logging as _logging
        for logger_name in [
            'chromadb', 'openai', 'httpx', 'httpcore', 'litellm.utils',
            'chromadb.segment.impl.vector.local_persistent_hnsw', 'utils'
        ]:
            get_logger(logger_name).setLevel(_logging.WARNING)

    def _init_protocol_driven_memory(self):
        """Initialize memory using adapter registry (protocol-driven approach)."""
        # Determine provider preference
        provider = self.cfg.get("provider", "sqlite").lower()
        self._log_verbose(f"Requested memory provider: {provider}")
        
        # Map legacy provider names to adapter names
        provider_mapping = {
            "rag": "chroma",  # Legacy "rag" provider uses ChromaDB
            "mem0": "mem0",
            "mongodb": "mongodb",
            "sqlite": "sqlite",
            "none": "in_memory"
        }
        
        adapter_name = provider_mapping.get(provider, provider)
        
        # Try to get preferred adapter, fallback to available ones
        adapter = get_memory_adapter(adapter_name, **self._get_adapter_config())
        
        if adapter is None:
            # Fallback to first available adapter
            self._log_verbose(f"Provider '{adapter_name}' not available, trying fallbacks")
            fallback_result = get_first_available_memory_adapter(
                preferences=["sqlite", "in_memory"],
                **self._get_adapter_config()
            )
            if fallback_result:
                adapter_name, adapter = fallback_result
                self._log_verbose(f"Using fallback adapter: {adapter_name}")
            else:
                raise RuntimeError("No memory adapters available")
        
        # Store adapter and metadata
        self.memory_adapter = adapter
        self.provider = adapter_name
        self._log_verbose(f"Initialized memory adapter: {adapter_name}")
        
        # Check if adapter supports advanced features
        self.graph_enabled = hasattr(adapter, 'graph_enabled') and adapter.graph_enabled
        self.use_embedding = adapter_name in ['chroma', 'mongodb']  # Vector-based adapters

    def _get_adapter_config(self) -> Dict[str, Any]:
        """Get configuration for adapter initialization."""
        config = self.cfg.copy()
        
        # Add embedding model configuration
        embedder_config = config.get("embedder", {})
        if isinstance(embedder_config, dict):
            embedder_model_config = embedder_config.get("config", {})
            config["embedding_model"] = embedder_model_config.get("model", "text-embedding-3-small")
        else:
            config["embedding_model"] = "text-embedding-3-small"
        
        # Add project data directory paths for file-based adapters
        from ..paths import get_project_data_dir
        project_data = str(get_project_data_dir())
        os.makedirs(project_data, exist_ok=True)
        
        config.setdefault("short_db", os.path.join(project_data, "short_term.db"))
        config.setdefault("long_db", os.path.join(project_data, "long_term.db"))
        config.setdefault("rag_db_path", os.path.join(project_data, "chroma_db"))
        
        return config

    def _init_legacy_compatibility(self):
        """Initialize legacy compatibility layer for direct SQLite access."""
        # For backward compatibility, maintain direct SQLite connections
        # This ensures existing code that accesses _get_stm_conn() still works
        from ..paths import get_project_data_dir
        project_data = str(get_project_data_dir())
        
        self.short_db = self.cfg.get("short_db", os.path.join(project_data, "short_term.db"))
        self.long_db = self.cfg.get("long_db", os.path.join(project_data, "long_term.db"))
        
        # Initialize SQLite adapter for legacy methods
        self._sqlite_adapter = SqliteMemoryAdapter(
            short_db=self.short_db,
            long_db=self.long_db,
            verbose=self.verbose
        )
        
        # Thread-local storage and locks (for legacy compatibility)
        self._local = self._sqlite_adapter._local
        self._write_lock = self._sqlite_adapter._write_lock
        self._all_connections = self._sqlite_adapter._all_connections
        self._connection_lock = self._sqlite_adapter._connection_lock

    def _log_verbose(self, msg: str, level: int = logging.INFO):
        """Only log if verbose >= 5"""
        if self.verbose >= 5:
            logger.log(level, msg)

    # -------------------------------------------------------------------------
    #                       Protocol-Driven Memory API
    # -------------------------------------------------------------------------

    def store_short_term(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
        completeness: float = None,
        relevance: float = None,
        clarity: float = None,
        accuracy: float = None,
        weights: Dict[str, float] = None,
        evaluator_quality: float = None
    ):
        """Store in short-term memory using configured adapter."""
        logger.info(f"Storing in short-term memory via {self.provider}, length: {len(text)} chars")
        
        # Process quality metrics
        metadata = self._process_quality_metrics(
            metadata, completeness, relevance, clarity,
            accuracy, weights, evaluator_quality
        )
        
        # Delegate to adapter
        result = self.memory_adapter.store_short_term(text, metadata=metadata)
        
        # Also store in legacy SQLite for backward compatibility
        self._sqlite_adapter.store_short_term(text, metadata=metadata)
        
        # Emit trace event
        self._emit_memory_event("store", "short_term", len(text), metadata=metadata)
        return result

    def search_short_term(
        self, 
        query: str, 
        limit: int = 5,
        min_quality: float = 0.0,
        relevance_cutoff: float = 0.0,
        rerank: bool = False,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search short-term memory using configured adapter."""
        self._log_verbose(f"Searching short memory via {self.provider} for: {query}")
        
        # Delegate to adapter
        results = self.memory_adapter.search_short_term(
            query, limit=limit, min_quality=min_quality,
            relevance_cutoff=relevance_cutoff, rerank=rerank, **kwargs
        )
        
        # Filter by quality if needed
        if min_quality > 0.0:
            results = [r for r in results if r.get("metadata", {}).get("quality", 0.0) >= min_quality]
        
        # Filter by relevance cutoff
        if relevance_cutoff > 0.0:
            results = [r for r in results if r.get("score", 1.0) >= relevance_cutoff]
        
        # Emit trace event
        top_score = results[0].get("score") if results else None
        self._emit_memory_event("search", "short_term", query=query,
                               result_count=len(results), top_score=top_score)
        
        return results

    def store_long_term(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
        completeness: float = None,
        relevance: float = None,
        clarity: float = None,
        accuracy: float = None,
        weights: Dict[str, float] = None,
        evaluator_quality: float = None
    ):
        """Store in long-term memory using configured adapter."""
        logger.info(f"Storing in long-term memory via {self.provider}, length: {len(text)} chars")
        
        # Process quality metrics
        metadata = self._process_quality_metrics(
            metadata, completeness, relevance, clarity,
            accuracy, weights, evaluator_quality
        )
        
        # Delegate to adapter
        result = self.memory_adapter.store_long_term(text, metadata=metadata)
        
        # Also store in legacy SQLite for backward compatibility
        self._sqlite_adapter.store_long_term(text, metadata=metadata)
        
        # Emit trace event
        self._emit_memory_event("store", "long_term", len(text), metadata=metadata)
        return result

    def search_long_term(
        self, 
        query: str, 
        limit: int = 5, 
        relevance_cutoff: float = 0.0,
        min_quality: float = 0.0,
        rerank: bool = False,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search long-term memory using configured adapter."""
        self._log_verbose(f"Searching long memory via {self.provider} for: {query}")
        
        # Delegate to adapter
        results = self.memory_adapter.search_long_term(
            query, limit=limit, min_quality=min_quality,
            relevance_cutoff=relevance_cutoff, rerank=rerank, **kwargs
        )
        
        # Filter by quality if needed
        if min_quality > 0.0:
            results = [r for r in results if r.get("metadata", {}).get("quality", 0.0) >= min_quality]
        
        # Filter by relevance cutoff
        if relevance_cutoff > 0.0:
            results = [r for r in results if r.get("score", 1.0) >= relevance_cutoff]
        
        # Emit trace event
        top_score = results[0].get("score") if results else None
        self._emit_memory_event("search", "long_term", query=query,
                               result_count=len(results), top_score=top_score)
        
        return results

    def get_all_memories(self) -> List[Dict[str, Any]]:
        """Get all memories using configured adapter."""
        try:
            return self.memory_adapter.get_all_memories()
        except AttributeError:
            # Fallback to SQLite adapter if current adapter doesn't support get_all_memories
            return self._sqlite_adapter.get_all_memories()

    def reset_short_term(self):
        """Clear short-term memory."""
        if hasattr(self.memory_adapter, 'reset_short_term'):
            self.memory_adapter.reset_short_term()
        # Also clear SQLite for backward compatibility
        self._sqlite_adapter.reset_short_term()

    def reset_long_term(self):
        """Clear long-term memory.""" 
        if hasattr(self.memory_adapter, 'reset_long_term'):
            self.memory_adapter.reset_long_term()
        # Also clear SQLite for backward compatibility
        self._sqlite_adapter.reset_long_term()

    def reset_all(self):
        """Clear all memory."""
        self.reset_short_term()
        self.reset_long_term()

    # -------------------------------------------------------------------------
    #                       Backward Compatibility Layer
    # -------------------------------------------------------------------------

    def _get_stm_conn(self):
        """Get thread-local short-term memory SQLite connection (legacy compatibility)."""
        return self._sqlite_adapter._get_stm_conn()

    def _get_ltm_conn(self):
        """Get thread-local long-term memory SQLite connection (legacy compatibility)."""
        return self._sqlite_adapter._get_ltm_conn()

    # Legacy properties for backward compatibility
    @property
    def use_mem0(self):
        """Backward compatibility: check if using mem0 provider."""
        return self.provider == "mem0"
    
    @property 
    def use_rag(self):
        """Backward compatibility: check if using chroma/rag provider."""
        return self.provider == "chroma"
    
    @property
    def use_mongodb(self):
        """Backward compatibility: check if using mongodb provider."""
        return self.provider == "mongodb"

    # -------------------------------------------------------------------------
    #                       Delegate Other Methods to Original Implementation  
    # -------------------------------------------------------------------------

    def _emit_memory_event(self, event_type: str, memory_type: str, 
                           content_length: int = 0, query: str = "", 
                           result_count: int = 0, top_score: float = None,
                           metadata: Dict[str, Any] = None):
        """Emit memory trace event if tracing is enabled (zero overhead when disabled)."""
        try:
            from ..trace.context_events import get_context_emitter
            emitter = get_context_emitter()
            if not emitter.enabled:
                return
            agent_name = self.cfg.get("agent_name", "unknown")
            if event_type == "store":
                emitter.memory_store(agent_name, memory_type, content_length, metadata)
            elif event_type == "search":
                emitter.memory_search(agent_name, query, result_count, memory_type, top_score)
        except Exception as e:
            # Silent fail - tracing should never break memory operations
            logger.debug(f"Memory trace emit failed: {e}")

    def _process_quality_metrics(
        self,
        metadata: Dict[str, Any],
        completeness: float = None,
        relevance: float = None,
        clarity: float = None, 
        accuracy: float = None,
        weights: Dict[str, float] = None,
        evaluator_quality: float = None
    ) -> Dict[str, Any]:
        """Process and store quality metrics in metadata."""
        metadata = metadata or {}
        
        # Handle sub-metrics if provided
        if None not in [completeness, relevance, clarity, accuracy]:
            metadata.update({
                "completeness": completeness,
                "relevance": relevance,
                "clarity": clarity,
                "accuracy": accuracy,
                "quality": self.compute_quality_score(
                    completeness, relevance, clarity, accuracy, weights
                )
            })
        # Handle external evaluator quality if provided
        elif evaluator_quality is not None:
            metadata["quality"] = evaluator_quality
        
        return metadata

    def compute_quality_score(
        self,
        completeness: float,
        relevance: float,
        clarity: float,
        accuracy: float,
        weights: Dict[str, float] = None
    ) -> float:
        """Combine multiple sub-metrics into one final score."""
        if not weights:
            weights = {
                "completeness": 0.25,
                "relevance": 0.25,
                "clarity": 0.25,
                "accuracy": 0.25
            }
        total = (completeness * weights["completeness"]
                 + relevance   * weights["relevance"]
                 + clarity     * weights["clarity"]
                 + accuracy    * weights["accuracy"]
                )
        return round(total, 3)

    # Delegate remaining methods to maintain full API compatibility
    # These methods can be gradually refactored to use adapters as needed

    def store_entity(self, name: str, type_: str, desc: str, relations: str = ""):
        """Store entity info in memory (delegates to long-term storage)."""
        data = f"Entity {name}({type_}): {desc} | relationships: {relations}"
        self.store_long_term(data, metadata={"category": "entity"})

    def search_entity(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Filter to items that have metadata 'category=entity'."""
        all_hits = self.search_long_term(query, limit=20)  # gather more
        return [h for h in all_hits if h.get("metadata", {}).get("category") == "entity"][:limit]

    def store_user_memory(self, user_id: str, text: str, extra: Dict[str, Any] = None):
        """Store user-specific memory."""
        meta = {"user_id": user_id}
        if extra:
            meta.update(extra)
        self.store_long_term(text, metadata=meta)

    def search_user_memory(self, user_id: str, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search user-specific memory."""
        hits = self.search_long_term(query, limit=20, **kwargs)
        return [h for h in hits if h.get("metadata", {}).get("user_id") == user_id][:limit]

    def search(self, query: str, user_id: Optional[str] = None, agent_id: Optional[str] = None, 
               run_id: Optional[str] = None, limit: int = 5, rerank: bool = False, **kwargs) -> List[Dict[str, Any]]:
        """Generic search method with user/agent/run scoping."""
        if user_id:
            return self.search_user_memory(user_id, query, limit=limit, rerank=rerank, **kwargs)
        else:
            return self.search_long_term(query, limit=limit, rerank=rerank, **kwargs)

    def close_connections(self):
        """Close database connections."""
        if hasattr(self.memory_adapter, 'close_connections'):
            self.memory_adapter.close_connections()
        self._sqlite_adapter.close_connections()

    def __enter__(self):
        """Allow Memory to be used as a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensure connections are closed when leaving a context manager block."""
        self.close_connections()

    def __del__(self):
        """Cleanup when instance is garbage-collected."""
        try:
            self.close_connections()
        except Exception:
            pass  # Best-effort cleanup