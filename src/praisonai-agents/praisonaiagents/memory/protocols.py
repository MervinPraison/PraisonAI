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
class DeletableMemoryProtocol(MemoryProtocol, Protocol):
    """
    Protocol for memory that supports selective deletion.
    
    Enables removing specific memories by ID without clearing all data.
    Essential for:
    - Privacy compliance (GDPR right to erasure)
    - Context window management (removing large image-based memories)
    - Correcting outdated information
    
    Example:
        ```python
        class MyMemory:
            def delete_memory(self, memory_id: str) -> bool:
                if memory_id in self._store:
                    del self._store[memory_id]
                    return True
                return False
            
            def delete_memories(self, memory_ids: List[str]) -> int:
                count = 0
                for mid in memory_ids:
                    if self.delete_memory(mid):
                        count += 1
                return count
        ```
    """
    
    def delete_memory(self, memory_id: str, memory_type: Optional[str] = None) -> bool:
        """
        Delete a specific memory by ID.
        
        Args:
            memory_id: The unique identifier of the memory to delete
            memory_type: Optional type hint (short_term, long_term, entity)
                        If None, searches all types.
            
        Returns:
            True if memory was found and deleted, False otherwise
        """
        ...
    
    def delete_memories(self, memory_ids: List[str]) -> int:
        """
        Delete multiple memories by their IDs.
        
        Args:
            memory_ids: List of memory IDs to delete
            
        Returns:
            Number of memories successfully deleted
        """
        ...


@runtime_checkable
class AsyncDeletableMemoryProtocol(Protocol):
    """
    Async Protocol for memory deletion operations.
    """
    
    async def adelete_memory(self, memory_id: str, memory_type: Optional[str] = None) -> bool:
        """Async delete a specific memory by ID."""
        ...
    
    async def adelete_memories(self, memory_ids: List[str]) -> int:
        """Async delete multiple memories by their IDs."""
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
    'DeletableMemoryProtocol',
    'AsyncDeletableMemoryProtocol',
    'AsyncMemoryProtocol',
    'EntityMemoryProtocol',
]

