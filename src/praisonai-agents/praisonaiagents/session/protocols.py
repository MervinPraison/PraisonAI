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
