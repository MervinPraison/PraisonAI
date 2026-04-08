"""
Legacy Memory Adapter

This adapter wraps the existing Memory class to provide backward compatibility
while demonstrating the protocol-driven approach. This allows the core Memory
class to be gradually refactored while maintaining all existing functionality.

This approach follows the Strangler Fig pattern:
1. Create adapters that wrap existing implementations
2. Register them in the adapter registry
3. Core classes use adapters via registry instead of direct imports
4. Gradually move logic from legacy class to clean adapters
"""

import os
import uuid
from typing import Any, Dict, List, Optional
from ..protocols import MemoryProtocol


class LegacyMemoryAdapter:
    """
    Adapter that wraps the existing Memory class to implement MemoryProtocol.
    
    This enables the existing Memory implementation to work through the
    adapter registry while we gradually refactor it to be more protocol-driven.
    """
    
    def __init__(self, **kwargs):
        """Initialize legacy memory adapter by wrapping existing Memory class."""
        # Import the original Memory class here to avoid circular imports
        from .. import memory as memory_module
        
        # Create instance of the original Memory class
        config = kwargs.get("config", kwargs)
        verbose = kwargs.get("verbose", 0)
        
        self._memory = memory_module.Memory(config=config, verbose=verbose)
    
    def store_short_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store in short-term memory via legacy Memory class."""
        self._memory.store_short_term(text, metadata=metadata, **kwargs)
        # Generate a stable UUID instead of using unstable id(text)
        return str(uuid.uuid4())
    
    def search_short_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search short-term memory via legacy Memory class."""
        return self._memory.search_short_term(query, limit=limit, **kwargs)
    
    def store_long_term(self, text: str, metadata: Optional[Dict[str, Any]] = None, **kwargs) -> str:
        """Store in long-term memory via legacy Memory class."""
        self._memory.store_long_term(text, metadata=metadata, **kwargs)
        # Generate a stable UUID instead of using unstable id(text)
        return str(uuid.uuid4())
    
    def search_long_term(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Search long-term memory via legacy Memory class."""
        return self._memory.search_long_term(query, limit=limit, **kwargs)
    
    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """Get all memories via legacy Memory class."""
        return self._memory.get_all_memories(**kwargs)


def create_legacy_memory_adapter(**kwargs) -> MemoryProtocol:
    """
    Factory function to create legacy memory adapter.
    
    This factory enables the existing Memory class to work through the
    adapter registry without requiring immediate refactoring.
    
    Args:
        **kwargs: Configuration passed to legacy Memory class
        
    Returns:
        MemoryProtocol adapter instance wrapping legacy Memory
    """
    return LegacyMemoryAdapter(**kwargs)