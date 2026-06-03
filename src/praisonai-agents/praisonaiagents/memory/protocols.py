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
            
            def get_all_memories(self, **kwargs):
                return self._data
        
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

    def get_all_memories(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Get all memories from all backends.
        
        Returns:
            List of all memory entries (short-term and long-term combined)
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


@runtime_checkable
class AgentMemoryProtocol(Protocol):
    """
    Protocol for memory implementations used by the Agent class.
    
    This defines the interface that Agent expects from its _memory_instance.
    Both FileMemory and Memory satisfy this protocol, enabling consistent
    usage across backends.
    
    Example:
        ```python
        class CustomMemory:
            def get_context(self, query=None):
                return "remembered facts here"
            
            def save_session(self, name, conversation_history=None, metadata=None):
                pass  # persist session
        
        agent = Agent(memory=CustomMemory())
        ```
    """
    
    def get_context(
        self,
        query: Optional[str] = None,
        **kwargs
    ) -> str:
        """Get memory context for injection into system prompt."""
        ...
    
    def save_session(
        self,
        name: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Save a conversation session to memory."""
        ...

    # ── New optional lifecycle hooks (default no-op) ──────────────────────

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Called before context compaction discards messages.

        Implementations should extract and persist any facts worth preserving
        from ``messages``. The return value is a short text summary that the
        compactor MAY include in the structured summary it generates.
        Called synchronously on the agent thread — keep it fast.
        
        Args:
            messages: List of message dictionaries about to be discarded
            
        Returns:
            Short text summary of extracted facts (optional)
        """
        return ""

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
    ) -> None:
        """Called when the active session ID changes.

        ``reset=True`` indicates a genuinely new conversation; ``False`` means
        a continuation lineage (post-compression rotation). Providers should
        update internal caches and route future writes to ``new_session_id``.
        
        Args:
            new_session_id: The new session identifier
            parent_session_id: The previous session identifier
            reset: Whether this is a fresh conversation (True) or continuation (False)
        """
        pass

    def on_memory_write(
        self,
        action: str,          # "add" | "replace" | "remove"
        target: str,          # "short_term" | "long_term" | "entity"
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when auto_memory or store_learning writes to built-in memory.

        Allows external providers to mirror built-in memory writes for
        cross-system consistency.
        
        Args:
            action: The type of operation ("add", "replace", "remove")
            target: The memory type being written to
            content: The content being stored
            metadata: Optional metadata for the memory entry
        """
        pass

    def on_delegation(
        self,
        task: str,
        result: str,
        *,
        agent_name: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called on the parent agent after a subagent completes a delegated task.

        Allows memory backends to incorporate subagent work into the parent's
        knowledge store without waiting for the parent to explicitly call store_*.
        
        Args:
            task: Description of the delegated task
            result: Result returned by the subagent
            agent_name: Name of the agent that performed the task
            metadata: Optional metadata about the delegation
        """
        pass


__all__ = [
    'MemoryProtocol',
    'ResettableMemoryProtocol',
    'DeletableMemoryProtocol',
    'AsyncDeletableMemoryProtocol',
    'AsyncMemoryProtocol',
    'EntityMemoryProtocol',
    'AgentMemoryProtocol',
]

