"""
Lightweight memory adapter for protocol-driven architecture.

This replaces the heavy memory implementation which has been moved to the wrapper package.
Now contains only lightweight protocol adapters that delegate to the wrapper implementation.

ARCHITECTURAL CHANGE:
- Removed: 2000+ lines of SQLite/ChromaDB/MongoDB implementation
- Removed: Global logging monkey-patching (logging.Logger.trace = trace)
- Removed: Import-time environment mutations (os.environ["LITELLM_TELEMETRY"] = "False")
- Removed: Custom lazy-loading patterns (replaced with centralized _lazy.py)
- Added: Lightweight protocol adapter that delegates to wrapper package
"""

import os
from typing import Any, Dict, List, Optional
import logging

# Import protocols - these stay in core
from .protocols import MemoryProtocol, AgentMemoryProtocol

# Use centralized lazy loading instead of custom patterns
from .._lazy import lazy_import

logger = logging.getLogger(__name__)


class Memory:
    """
    Lightweight memory adapter that delegates to wrapper implementation.
    
    This maintains backward compatibility while following protocol-driven architecture.
    The actual heavy implementation (SQLite, ChromaDB, MongoDB) is in the wrapper package.
    """
    
    def __init__(self, cfg: Dict[str, Any] = None):
        """Initialize lightweight memory adapter."""
        self._cfg = dict(cfg or {})
        self._wrapper_memory = None

        # Apply project-relative defaults for database paths so they are
        # placed under the project data directory (not the cwd).
        if "short_db" not in self._cfg or "long_db" not in self._cfg:
            try:
                from ..paths import get_project_data_dir
                _project_data = str(get_project_data_dir())
                self._cfg.setdefault("short_db", os.path.join(_project_data, "short_term.db"))
                self._cfg.setdefault("long_db", os.path.join(_project_data, "long_term.db"))
            except Exception:
                pass  # keep caller-provided or default paths
    
    def _get_wrapper_memory(self):
        """Lazy load the wrapper memory implementation."""
        if self._wrapper_memory is None:
            try:
                # Lazy import from wrapper package
                WrapperMemory = lazy_import('praisonai.memory', 'Memory')
                self._wrapper_memory = WrapperMemory(self._cfg)
            except (ImportError, AttributeError):
                # Fallback to minimal in-memory implementation
                logger.warning("Wrapper memory not available, using minimal fallback")
                self._wrapper_memory = _MinimalMemory(self._cfg)
        return self._wrapper_memory
    
    # MemoryProtocol implementation - delegate to wrapper
    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store content in short-term memory."""
        return self._get_wrapper_memory().store_short_term(text, metadata, **kwargs)
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search short-term memory."""
        return self._get_wrapper_memory().search_short_term(query, limit, **kwargs)
    
    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store content in long-term memory."""
        return self._get_wrapper_memory().store_long_term(text, metadata, **kwargs)
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search long-term memory."""
        return self._get_wrapper_memory().search_long_term(query, limit, **kwargs)
    
    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all memories from all backends."""
        return self._get_wrapper_memory().get_all_memories(**kwargs)
    
    # AgentMemoryProtocol implementation - delegate to wrapper
    def get_context(self, query: Optional[str] = None, **kwargs) -> str:
        """Get memory context for injection into system prompt."""
        return self._get_wrapper_memory().get_context(query, **kwargs)
    
    def save_session(self, name: str, conversation_history: Optional[List[Dict[str, Any]]] = None,
                    metadata: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """Save a conversation session to memory."""
        self._get_wrapper_memory().save_session(name, conversation_history, metadata, **kwargs)
    
    # Context manager support
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self._wrapper_memory, 'close_connections'):
            self._wrapper_memory.close_connections()


class _MinimalMemory:
    """Minimal in-memory fallback when wrapper is not available."""
    
    def __init__(self, cfg: Dict[str, Any] = None):
        self._short_term = []
        self._long_term = []
    
    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        entry = {"id": str(len(self._short_term)), "content": text, "metadata": metadata or {}}
        self._short_term.append(entry)
        return entry["id"]
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        results = [entry for entry in self._short_term if query.lower() in entry["content"].lower()]
        return results[:limit]
    
    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        entry = {"id": str(len(self._long_term)), "content": text, "metadata": metadata or {}}
        self._long_term.append(entry)
        return entry["id"]
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        results = [entry for entry in self._long_term if query.lower() in entry["content"].lower()]
        return results[:limit]
    
    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        return self._short_term + self._long_term
    
    def get_context(self, query: Optional[str] = None, **kwargs) -> str:
        if query:
            memories = self.search_short_term(query, 3) + self.search_long_term(query, 3)
        else:
            memories = (self._short_term[-3:] if self._short_term else []) + (self._long_term[-3:] if self._long_term else [])
        
        if not memories:
            return ""
        
        context_parts = []
        for mem in memories:
            context_parts.append(f"- {mem['content']}")
        
        return "Relevant memories:\n" + "\n".join(context_parts)
    
    def save_session(self, name: str, conversation_history: Optional[List[Dict[str, Any]]] = None,
                    metadata: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        # Minimal implementation - just store as long-term memory
        if conversation_history:
            for msg in conversation_history:
                if msg.get('content'):
                    meta = {**(metadata or {}), 'session': name, 'role': msg.get('role', 'unknown')}
                    self.store_long_term(msg['content'], meta)


# ARCHITECTURAL FIX: Removed global logging monkey-patch
# Before: logging.Logger.trace = trace
# This violated protocol-driven architecture by modifying global Logger class for entire process