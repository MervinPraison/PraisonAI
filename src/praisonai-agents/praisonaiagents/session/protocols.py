"""
Session Store Protocol for PraisonAI Agents.

Defines the minimal interface contract for session persistence backends.
Any class implementing these methods can be used as a session store.

Built-in implementations:
- DefaultSessionStore (JSON file-based)
- HierarchicalSessionStore (extends DefaultSessionStore with fork/snapshot)

Custom implementations (e.g. Redis, MongoDB, PostgreSQL) can implement
this protocol for seamless swapping.

Usage:
    from praisonaiagents.session.protocols import SessionStoreProtocol
    
    class RedisSessionStore:
        def add_message(self, session_id, role, content, metadata=None):
            ...  # Store in Redis
        
        def get_chat_history(self, session_id, max_messages=None):
            ...  # Retrieve from Redis
        
        # ... other methods
    
    # Type-check at runtime
    store: SessionStoreProtocol = RedisSessionStore()
    assert isinstance(store, SessionStoreProtocol)
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Protocol for session persistence backends.
    
    Defines the minimal interface for storing and retrieving
    agent conversation sessions. Implementations must provide
    these five core methods.
    
    Built-in implementations:
    - DefaultSessionStore (JSON files with atomic writes)
    - HierarchicalSessionStore (fork, snapshot, revert)
    
    Example custom implementation::
    
        class MyStore:
            def add_message(self, session_id, role, content, metadata=None):
                ...
            def get_chat_history(self, session_id, max_messages=None):
                return [{"role": "user", "content": "Hi"}]
            def clear_session(self, session_id):
                return True
            def delete_session(self, session_id):
                return True
            def session_exists(self, session_id):
                return False
        
        store: SessionStoreProtocol = MyStore()
        assert isinstance(store, SessionStoreProtocol)  # True
    """
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a message to a session.
        
        Args:
            session_id: Unique session identifier.
            role: Message role ("user", "assistant", "system").
            content: Message content text.
            metadata: Optional metadata dict.
            
        Returns:
            True if saved successfully.
        """
        ...
    
    def get_chat_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Get chat history in LLM-compatible format.
        
        Args:
            session_id: Unique session identifier.
            max_messages: Maximum messages to return (most recent).
            
        Returns:
            List of {"role": "...", "content": "..."} dicts.
        """
        ...
    
    def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session (keep session metadata).
        
        Args:
            session_id: Unique session identifier.
            
        Returns:
            True if cleared successfully.
        """
        ...
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session completely (data + metadata).
        
        Args:
            session_id: Unique session identifier.
            
        Returns:
            True if deleted successfully.
        """
        ...
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.
        
        Args:
            session_id: Unique session identifier.
            
        Returns:
            True if the session exists.
        """
        ...


@runtime_checkable
class RuntimeStateMirroringProtocol(Protocol):
    """Protocol for runtime state mirroring in sessions (Issue #1943).
    
    Enables native runtime to persist lightweight runtime-specific execution 
    artifacts for replay, debugging, or cross-turn mirroring when users mix 
    runtimes in one session.
    """
    
    def set_runtime_state(
        self, 
        session_id: str, 
        runtime_id: str, 
        turn_id: str, 
        state: Dict[str, Any]
    ) -> bool:
        """Set runtime state for a specific runtime and turn.
        
        Args:
            session_id: Session identifier
            runtime_id: Runtime identifier (e.g., "native", "plugin_harness") 
            turn_id: Turn identifier within the runtime
            state: Runtime state data (tool call ids, transcript slices, etc.)
            
        Returns:
            True if saved successfully
        """
        ...
    
    def get_runtime_state(
        self, 
        session_id: str, 
        runtime_id: str, 
        turn_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get runtime state for a specific runtime and optionally a turn.
        
        Args:
            session_id: Session identifier
            runtime_id: Runtime identifier
            turn_id: Optional turn identifier (if None, returns all turns for runtime)
            
        Returns:
            Runtime state data
        """
        ...
    
    def clear_runtime_state(
        self, 
        session_id: str, 
        runtime_id: Optional[str] = None
    ) -> bool:
        """Clear runtime state for a session, optionally filtered by runtime_id.
        
        Args:
            session_id: Session identifier
            runtime_id: Optional runtime identifier (if None, clears all runtime state)
            
        Returns:
            True if cleared successfully
        """
        ...


@runtime_checkable
class CheckpointQueryProtocol(Protocol):
    """Read path for session checkpoints / rollback snapshots."""

    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """Return checkpoint metadata for a session."""
        ...

    def get_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Return a single checkpoint payload."""
        ...
