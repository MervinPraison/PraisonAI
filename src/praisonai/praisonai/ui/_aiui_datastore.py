"""Bridge praisonaiagents SessionStore → aiui BaseDataStore.

Allows any SessionStoreProtocol implementation (file/Redis/Mongo) to back
the aiui dashboard's Sessions page. No Chainlit required.

This adapter enables PraisonAI's native session persistence to power
the aiui dashboard, maintaining consistency with Core SDK storage.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional, Dict, List

try:
    from praisonaiui.datastore import BaseDataStore
except ImportError:
    # Graceful fallback for when aiui is not available
    class BaseDataStore:
        """Fallback BaseDataStore for when aiui is not installed."""
        pass

try:
    from praisonaiagents.session import (
        SessionStoreProtocol,
        get_hierarchical_session_store,
    )
except ImportError:
    # Graceful fallback for when praisonaiagents is not available
    SessionStoreProtocol = None
    get_hierarchical_session_store = None


class PraisonAISessionDataStore(BaseDataStore):
    """Adapter that bridges SessionStoreProtocol → aiui BaseDataStore.
    
    This allows any PraisonAI SessionStore implementation (file-based,
    Redis, MongoDB, etc.) to serve as the persistence layer for aiui
    dashboard sessions.
    
    Args:
        store: SessionStoreProtocol implementation. If None, uses
               get_hierarchical_session_store() as default.
    
    Example:
        from praisonai.ui._aiui_datastore import PraisonAISessionDataStore
        import praisonaiui as aiui
        
        # Use default hierarchical store
        aiui.set_datastore(PraisonAISessionDataStore())
        
        # Or provide custom store
        from my_project import MyRedisStore
        aiui.set_datastore(PraisonAISessionDataStore(MyRedisStore()))
    """
    
    def __init__(self, store: Optional[SessionStoreProtocol] = None):
        if SessionStoreProtocol is None:
            raise ImportError(
                "praisonaiagents is required to use PraisonAISessionDataStore. "
                "Install with: pip install praisonaiagents"
            )
        
        if store is None and get_hierarchical_session_store is None:
            raise ImportError(
                "praisonaiagents.session.get_hierarchical_session_store is required. "
                "Install with: pip install praisonaiagents"
            )
        
        self._store = store or get_hierarchical_session_store()
    
    def _new_id(self) -> str:
        """Generate a new unique session ID."""
        return str(uuid.uuid4())
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all available sessions.
        
        Note: SessionStoreProtocol doesn't expose a list_sessions method,
        so this is a limitation. For file-based stores, we could potentially
        scan the filesystem, but that would be implementation-specific.
        
        For now, return empty list. Users will need to know their session IDs
        or create new sessions.
        """
        # TODO: If needed, could add optional list_sessions to SessionStoreProtocol
        # For now, return empty - sessions are created on-demand
        return []
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID.
        
        Args:
            session_id: Session identifier.
            
        Returns:
            Session dict with 'id' and 'messages' fields, or None if not found.
        """
        if not self._store.session_exists(session_id):
            return None
        
        messages = self._store.get_chat_history(session_id)
        return {
            "id": session_id,
            "messages": messages,
            "metadata": {
                "created_via": "praisonai",
                "message_count": len(messages),
            },
        }
    
    async def create_session(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new session.
        
        Args:
            session_id: Optional session ID. If None, generates a new UUID.
            
        Returns:
            Session dict with 'id' and empty 'messages' list.
        """
        sid = session_id or self._new_id()
        
        # SessionStoreProtocol creates sessions lazily on first add_message,
        # so we don't need to explicitly create here
        return {
            "id": sid,
            "messages": [],
            "metadata": {
                "created_via": "praisonai",
                "message_count": 0,
            },
        }
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session completely.
        
        Args:
            session_id: Session identifier.
            
        Returns:
            True if deleted successfully.
        """
        return self._store.delete_session(session_id)
    
    async def add_message(
        self, 
        session_id: str, 
        message: Dict[str, Any]
    ) -> bool:
        """Add a message to a session.
        
        Args:
            session_id: Session identifier.
            message: Message dict with 'role', 'content', and optional 'metadata'.
            
        Returns:
            True if added successfully.
        """
        role = message.get("role", "user")
        content = message.get("content", "")
        metadata = message.get("metadata")
        
        return self._store.add_message(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata,
        )
    
    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a session.
        
        Args:
            session_id: Session identifier.
            
        Returns:
            List of message dicts in LLM-compatible format.
        """
        return self._store.get_chat_history(session_id)
    
    async def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session (keep metadata).
        
        Args:
            session_id: Session identifier.
            
        Returns:
            True if cleared successfully.
        """
        return self._store.clear_session(session_id)