"""
Storage Protocol Definitions for PraisonAI Agents.

Provides Protocol interfaces for storage implementations to enable:
- DRY: Common storage patterns shared across modules
- Mocking: Easy testing without real file I/O
- Extensibility: Custom storage backends

These protocols are lightweight and have zero performance impact.
"""
from typing import Protocol, runtime_checkable, List, Dict, Any, TypeVar
from pathlib import Path
from datetime import datetime


T = TypeVar('T')


@runtime_checkable
class SessionInfoProtocol(Protocol):
    """
    Protocol for session/trace info.
    
    Defines the minimal interface for session metadata.
    Used by TrainingSessionInfo, TraceInfo, and similar classes.
    """
    session_id: str
    path: Path
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        ...


@runtime_checkable
class JSONStoreProtocol(Protocol):
    """
    Protocol for JSON-based storage.
    
    Defines the interface for persistent JSON storage.
    Implementations include BaseStore, TrainingStorage, etc.
    
    Example:
        ```python
        class MockStore:
            storage_path = Path("/tmp/mock.json")
            
            def load(self):
                return {}
            
            def save(self, data):
                pass
            
            def exists(self):
                return True
        
        # Use in tests
        store: JSONStoreProtocol = MockStore()
        ```
    """
    storage_path: Path
    
    def load(self) -> Dict[str, Any]:
        """Load data from storage."""
        ...
    
    def save(self, data: Dict[str, Any]) -> None:
        """Save data to storage."""
        ...
    
    def exists(self) -> bool:
        """Check if storage file exists."""
        ...


@runtime_checkable
class ListableStoreProtocol(Protocol):
    """
    Protocol for stores that support listing sessions.
    """
    
    def list_sessions(self, limit: int = 50) -> List[Any]:
        """List all sessions with metadata."""
        ...


@runtime_checkable
class CleanableStoreProtocol(Protocol):
    """
    Protocol for stores that support cleanup.
    """
    
    def cleanup(self, max_age_days: int = 30, max_size_mb: int = 100) -> int:
        """
        Clean up old entries.
        
        Args:
            max_age_days: Delete entries older than this
            max_size_mb: Delete oldest if total size exceeds this
            
        Returns:
            Number of entries deleted
        """
        ...


@runtime_checkable
class StorageBackendProtocol(Protocol):
    """
    Protocol for pluggable storage backends.
    
    Enables switching between file-based and database-based storage.
    Default implementation uses JSON files, but can be swapped for:
    - SQLite (lightweight, local)
    - PostgreSQL (production, scalable)
    - Redis (fast, ephemeral)
    - MongoDB (document-oriented)
    
    PraisonAI supports many databases through praisonaiagents.db adapters.
    This protocol allows storage classes to use any backend.
    
    Example:
        ```python
        class SQLiteBackend:
            def __init__(self, db_path: str):
                self.db_path = db_path
            
            def save(self, key: str, data: Dict[str, Any]) -> None:
                # Save to SQLite
                pass
            
            def load(self, key: str) -> Optional[Dict[str, Any]]:
                # Load from SQLite
                return {}
            
            def delete(self, key: str) -> bool:
                return True
            
            def list_keys(self, prefix: str = "") -> List[str]:
                return []
            
            def exists(self, key: str) -> bool:
                return True
        
        # Use with any storage class
        backend: StorageBackendProtocol = SQLiteBackend("data.db")
        ```
    """
    
    def save(self, key: str, data: Dict[str, Any]) -> None:
        """
        Save data with the given key.
        
        Args:
            key: Unique identifier for the data
            data: Dictionary to save
        """
        ...
    
    def load(self, key: str) -> Any:
        """
        Load data by key.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            The stored data, or None if not found
        """
        ...
    
    def delete(self, key: str) -> bool:
        """
        Delete data by key.
        
        Args:
            key: Unique identifier for the data
            
        Returns:
            True if deleted, False if not found
        """
        ...
    
    def list_keys(self, prefix: str = "") -> List[str]:
        """
        List all keys, optionally filtered by prefix.
        
        Args:
            prefix: Optional prefix to filter keys
            
        Returns:
            List of matching keys
        """
        ...
    
    def exists(self, key: str) -> bool:
        """
        Check if a key exists.
        
        Args:
            key: Unique identifier to check
            
        Returns:
            True if exists, False otherwise
        """
        ...


@runtime_checkable
class AsyncStorageBackendProtocol(Protocol):
    """
    Async Protocol for pluggable storage backends.
    
    Async version of StorageBackendProtocol for use in async contexts.
    """
    
    async def save(self, key: str, data: Dict[str, Any]) -> None:
        """Save data with the given key."""
        ...
    
    async def load(self, key: str) -> Any:
        """Load data by key."""
        ...
    
    async def delete(self, key: str) -> bool:
        """Delete data by key."""
        ...
    
    async def list_keys(self, prefix: str = "") -> List[str]:
        """List all keys, optionally filtered by prefix."""
        ...
    
    async def exists(self, key: str) -> bool:
        """Check if a key exists."""
        ...


__all__ = [
    'SessionInfoProtocol',
    'JSONStoreProtocol',
    'ListableStoreProtocol',
    'CleanableStoreProtocol',
    'StorageBackendProtocol',
    'AsyncStorageBackendProtocol',
]
