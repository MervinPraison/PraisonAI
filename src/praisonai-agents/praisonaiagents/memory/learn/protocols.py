"""
Learn Protocol Definitions.

Provides Protocol interfaces for learning implementations.
Enables custom learning backends and extensibility.
"""
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# Re-export LearnMode from feature_configs (canonical location)
# This avoids duplication while maintaining backward compatibility
from ...config.feature_configs import LearnMode


@runtime_checkable
class LearnProtocol(Protocol):
    """
    Protocol for learning store implementations.
    
    Enables custom backends (file, SQLite, Redis, MongoDB, etc.)
    while maintaining a consistent interface.
    
    Example:
        ```python
        class RedisLearnStore:
            def add(self, content: str, metadata=None) -> Dict[str, Any]:
                # Store in Redis
                return {"id": "...", "content": content}
            
            def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
                # Search Redis
                return []
            
            def list_all(self, limit: int = 100) -> List[Dict[str, Any]]:
                return []
            
            def delete(self, entry_id: str) -> bool:
                return True
            
            def clear(self) -> int:
                return 0
        ```
    """
    
    def add(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add a new entry to the store.
        
        Args:
            content: The content to store
            metadata: Optional metadata dictionary
            
        Returns:
            Dictionary with entry details including 'id'
        """
        ...
    
    def search(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search entries by query.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            
        Returns:
            List of matching entries
        """
        ...
    
    def list_all(
        self,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List all entries.
        
        Args:
            limit: Maximum entries to return
            
        Returns:
            List of all entries (most recent first)
        """
        ...
    
    def get(
        self,
        entry_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get entry by ID.
        
        Args:
            entry_id: Entry identifier
            
        Returns:
            Entry dict or None if not found
        """
        ...
    
    def update(
        self,
        entry_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing entry.
        
        Args:
            entry_id: Entry identifier
            content: New content
            metadata: Optional metadata to merge
            
        Returns:
            Updated entry or None if not found
        """
        ...
    
    def delete(
        self,
        entry_id: str,
    ) -> bool:
        """
        Delete an entry.
        
        Args:
            entry_id: Entry identifier
            
        Returns:
            True if deleted, False if not found
        """
        ...
    
    def clear(self) -> int:
        """
        Clear all entries.
        
        Returns:
            Number of entries cleared
        """
        ...


@runtime_checkable
class AsyncLearnProtocol(Protocol):
    """
    Async Protocol for learning store implementations.
    
    For backends that support async operations.
    """
    
    async def aadd(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Async add entry."""
        ...
    
    async def asearch(
        self,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Async search entries."""
        ...
    
    async def alist_all(
        self,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Async list all entries."""
        ...
    
    async def aget(
        self,
        entry_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Async get entry by ID."""
        ...
    
    async def aupdate(
        self,
        entry_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Async update entry."""
        ...
    
    async def adelete(
        self,
        entry_id: str,
    ) -> bool:
        """Async delete entry."""
        ...
    
    async def aclear(self) -> int:
        """Async clear all entries."""
        ...


@runtime_checkable
class LearnManagerProtocol(Protocol):
    """
    Protocol for LearnManager implementations.
    
    Defines the interface for managing learning across multiple stores.
    """
    
    def capture_persona(self, content: str, category: str = "general") -> Optional[Dict[str, Any]]:
        """Capture user preference or profile information."""
        ...
    
    def capture_insight(self, content: str, source: str = "interaction") -> Optional[Dict[str, Any]]:
        """Capture an observation or learning."""
        ...
    
    def capture_pattern(self, pattern: str, pattern_type: str = "general") -> Optional[Dict[str, Any]]:
        """Capture a reusable knowledge pattern."""
        ...
    
    def get_learning_context(self, limit_per_store: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """Get learning context from all enabled stores."""
        ...
    
    def search(self, query: str, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        """Search across all enabled stores."""
        ...
    
    def to_system_prompt_context(self) -> str:
        """Generate context for system prompt injection."""
        ...
    
    def process_conversation(
        self,
        messages: List[Dict[str, Any]],
        llm: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a conversation to extract learnings automatically.
        
        Args:
            messages: Conversation messages
            llm: Optional LLM model to use for extraction
            
        Returns:
            Dictionary with extracted learnings
        """
        ...


__all__ = [
    'LearnMode',
    'LearnProtocol',
    'AsyncLearnProtocol',
    'LearnManagerProtocol',
]
