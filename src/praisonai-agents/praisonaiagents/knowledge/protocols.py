"""
Knowledge Store Protocol for PraisonAI Agents.

Defines the interface that knowledge backends must implement.
Uses typing.Protocol for structural subtyping (duck typing with type hints).

No heavy imports - only stdlib typing.
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from .models import AddResult, SearchResult, SearchResultItem


@runtime_checkable
class KnowledgeStoreProtocol(Protocol):
    """
    Protocol defining the interface for knowledge store backends.
    
    Implementations include:
    - Mem0Adapter (mem0 backend)
    - ChromaAdapter (direct chromadb)
    - InternalAdapter (built-in storage)
    
    All implementations MUST:
    1. Return SearchResult/SearchResultItem with metadata as dict (never None)
    2. Handle identifier scoping (user_id/agent_id/run_id) appropriately
    3. Provide clear error messages for missing required parameters
    """
    
    def search(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> SearchResult:
        """
        Search for relevant content.
        
        Args:
            query: Search query string
            user_id: Optional user identifier for scoping
            agent_id: Optional agent identifier for scoping
            run_id: Optional run identifier for scoping
            limit: Maximum number of results
            filters: Optional metadata filters
            **kwargs: Backend-specific options
            
        Returns:
            SearchResult with normalized items (metadata always dict)
        """
        ...
    
    def add(
        self,
        content: Any,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AddResult:
        """
        Add content to the knowledge store.
        
        Args:
            content: Content to add (string, file path, or structured data)
            user_id: Optional user identifier for scoping
            agent_id: Optional agent identifier for scoping
            run_id: Optional run identifier for scoping
            metadata: Optional metadata to attach
            **kwargs: Backend-specific options
            
        Returns:
            AddResult with operation status
        """
        ...
    
    def get(
        self,
        item_id: str,
        **kwargs: Any,
    ) -> Optional[SearchResultItem]:
        """
        Get a specific item by ID.
        
        Args:
            item_id: ID of the item to retrieve
            **kwargs: Backend-specific options
            
        Returns:
            SearchResultItem if found, None otherwise
        """
        ...
    
    def get_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> SearchResult:
        """
        Get all items, optionally filtered by scope.
        
        Args:
            user_id: Optional user identifier for scoping
            agent_id: Optional agent identifier for scoping
            run_id: Optional run identifier for scoping
            limit: Maximum number of results
            **kwargs: Backend-specific options
            
        Returns:
            SearchResult with all matching items
        """
        ...
    
    def update(
        self,
        item_id: str,
        content: Any,
        **kwargs: Any,
    ) -> AddResult:
        """
        Update an existing item.
        
        Args:
            item_id: ID of the item to update
            content: New content
            **kwargs: Backend-specific options
            
        Returns:
            AddResult with operation status
        """
        ...
    
    def delete(
        self,
        item_id: str,
        **kwargs: Any,
    ) -> bool:
        """
        Delete an item by ID.
        
        Args:
            item_id: ID of the item to delete
            **kwargs: Backend-specific options
            
        Returns:
            True if deleted, False otherwise
        """
        ...
    
    def delete_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """
        Delete all items matching scope.
        
        Args:
            user_id: Optional user identifier for scoping
            agent_id: Optional agent identifier for scoping
            run_id: Optional run identifier for scoping
            **kwargs: Backend-specific options
            
        Returns:
            True if operation succeeded
        """
        ...


class KnowledgeBackendError(Exception):
    """Base exception for knowledge backend errors."""
    pass


class ScopeRequiredError(KnowledgeBackendError):
    """Raised when required scope identifiers are missing."""
    
    def __init__(self, message: str = None, backend: str = None):
        self.backend = backend
        default_msg = (
            f"At least one of 'user_id', 'agent_id', or 'run_id' must be provided"
            f"{f' for {backend} backend' if backend else ''}."
        )
        super().__init__(message or default_msg)


class BackendNotAvailableError(KnowledgeBackendError):
    """Raised when a requested backend is not available."""
    
    def __init__(self, backend: str, reason: str = None):
        self.backend = backend
        self.reason = reason
        msg = f"Knowledge backend '{backend}' is not available"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
