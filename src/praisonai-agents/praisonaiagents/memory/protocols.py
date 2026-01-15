"""
Memory Protocol Definitions.

Provides Protocol interfaces that define the minimal contract for memory implementations.
This enables:
- Mocking memory in tests without real database dependencies
- Creating custom memory backends (Redis, PostgreSQL, etc.)
- Type checking with static analyzers

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, Optional, Any, Dict, List


@runtime_checkable
class MemoryProtocol(Protocol):
    """
    Minimal Protocol for memory implementations.
    
    This defines the essential interface that any memory backend must provide.
    It enables proper mocking and testing without real database dependencies.
    
    Example:
        ```python
        # Create a simple in-memory store for testing
        class InMemoryStore:
            def __init__(self):
                self._data = []
            
            def store_short_term(self, text: str, metadata=None, **kwargs) -> str:
                self._data.append({"text": text, "type": "short"})
                return str(len(self._data))
            
            def search_short_term(self, query: str, limit: int = 5, **kwargs):
                return self._data[:limit]
            
            def store_long_term(self, text: str, metadata=None, **kwargs) -> str:
                self._data.append({"text": text, "type": "long"})
                return str(len(self._data))
            
            def search_long_term(self, query: str, limit: int = 5, **kwargs):
                return self._data[:limit]
        
        # Use in agent
        memory: MemoryProtocol = InMemoryStore()
        ```
    """
    
    def store_short_term(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Store content in short-term memory.
        
        Args:
            text: The content to store
            metadata: Optional metadata dictionary
            **kwargs: Additional backend-specific parameters
            
        Returns:
            An identifier for the stored content
        """
        ...
    
    def search_short_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search short-term memory.
        
        Args:
            query: The search query
            limit: Maximum number of results
            **kwargs: Additional backend-specific parameters
            
        Returns:
            List of matching memory entries
        """
        ...
    
    def store_long_term(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Store content in long-term memory.
        
        Args:
            text: The content to store
            metadata: Optional metadata dictionary
            **kwargs: Additional backend-specific parameters
            
        Returns:
            An identifier for the stored content
        """
        ...
    
    def search_long_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Search long-term memory.
        
        Args:
            query: The search query
            limit: Maximum number of results
            **kwargs: Additional backend-specific parameters
            
        Returns:
            List of matching memory entries
        """
        ...


@runtime_checkable
class ResettableMemoryProtocol(MemoryProtocol, Protocol):
    """
    Extended Protocol for memory that can be reset/cleared.
    """
    
    def reset_short_term(self) -> None:
        """Clear all short-term memory."""
        ...
    
    def reset_long_term(self) -> None:
        """Clear all long-term memory."""
        ...


@runtime_checkable
class AsyncMemoryProtocol(Protocol):
    """
    Async Protocol for memory implementations.
    
    For memory backends that support async operations.
    """
    
    async def astore_short_term(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Async store in short-term memory."""
        ...
    
    async def asearch_short_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Async search short-term memory."""
        ...
    
    async def astore_long_term(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """Async store in long-term memory."""
        ...
    
    async def asearch_long_term(
        self, 
        query: str, 
        limit: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Async search long-term memory."""
        ...


@runtime_checkable
class EntityMemoryProtocol(Protocol):
    """
    Protocol for memory that supports entity storage.
    """
    
    def store_entity(
        self, 
        name: str, 
        type_: str, 
        desc: str,
        relations: str = ""
    ) -> str:
        """Store an entity in memory."""
        ...
    
    def get_entity(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve an entity by name."""
        ...


__all__ = [
    'MemoryProtocol',
    'ResettableMemoryProtocol',
    'AsyncMemoryProtocol',
    'EntityMemoryProtocol',
]
