"""Bridge praisonaiagents SessionStore → aiui BaseDataStore.

Allows any SessionStoreProtocol implementation (file/Redis/Mongo) to back
the aiui dashboard's Sessions page. No Chainlit required.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Module-level cached implementation class
_impl_cls = None


def _build_impl_cls():
    """Build the implementation class with BaseDataStore inheritance.
    
    Thread-safe lazy class factory that imports BaseDataStore and creates
    a proper subclass. This avoids runtime __bases__ mutation and ensures
    BaseDataStore.__init__ is properly called.
    """
    global _impl_cls
    if _impl_cls is not None:
        return _impl_cls
    
    try:
        from praisonaiui.datastore import BaseDataStore
    except ImportError as e:
        raise ImportError(
            "praisonaiui is required for PraisonAISessionDataStore. "
            "Install with: pip install 'praisonai[ui]'"
        ) from e
    
    try:
        from praisonaiagents.session import get_hierarchical_session_store
    except ImportError as e:
        raise ImportError(
            "praisonaiagents is required for PraisonAISessionDataStore. "
            "Install with: pip install praisonaiagents"
        ) from e

    class _PraisonAISessionDataStoreImpl(BaseDataStore):
        """Implementation class that properly inherits from BaseDataStore."""
        
        def __init__(self, store: Optional[Any] = None):
            """Initialize with an optional session store, defaults to hierarchical store.
            
            Args:
                store: Optional SessionStoreProtocol implementation
            """
            super().__init__()  # Properly call BaseDataStore.__init__()
            self._store = store or get_hierarchical_session_store()

        def _new_id(self) -> str:
            """Generate a new session ID."""
            return str(uuid.uuid4())

        async def list_sessions(self) -> list[dict[str, Any]]:
            """List all available sessions."""
            # Check if store supports listing (DefaultSessionStore/HierarchicalSessionStore do)
            list_fn = getattr(self._store, "list_sessions", None)
            if list_fn is None:
                return []  # Protocol implementation doesn't support listing
            
            try:
                # DefaultSessionStore/HierarchicalSessionStore return list[dict]
                return list_fn(limit=50) or []
            except Exception:
                logger.exception("Failed to list sessions")
                return []

        async def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
            """Get a specific session by ID."""
            if not self._store.session_exists(session_id):
                return None
            
            try:
                chat_history = self._store.get_chat_history(session_id)
                return {
                    "id": session_id,
                    "messages": chat_history or [],
                }
            except Exception:
                logger.exception("Failed to load session %s", session_id)
                return None

        async def create_session(self, session_id: Optional[str] = None) -> dict[str, Any]:
            """Create a new session."""
            sid = session_id or self._new_id()
            # Sessions are created lazily on first add_message
            return {
                "id": sid,
                "messages": []
            }

        async def delete_session(self, session_id: str) -> bool:
            """Delete a session and return success status."""
            try:
                return self._store.delete_session(session_id)
            except Exception:
                logger.exception("Failed to delete session %s", session_id)
                return False

        async def add_message(self, session_id: str, message: dict[str, Any]):
            """Add a message to a session."""
            self._store.add_message(
                session_id=session_id,
                role=message.get("role", "user"),
                content=message.get("content", ""),
                metadata=message.get("metadata")
            )

        async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
            """Get all messages for a session."""
            if not self._store.session_exists(session_id):
                return []
            
            try:
                return self._store.get_chat_history(session_id) or []
            except Exception:
                logger.exception("Failed to load messages for session %s", session_id)
                return []

    _impl_cls = _PraisonAISessionDataStoreImpl
    return _impl_cls


class PraisonAISessionDataStore:
    """Adapter that bridges PraisonAI SessionStoreProtocol to aiui BaseDataStore.
    
    Dependency imports are deferred until instantiation to allow test
    collection without optional modules installed.
    """
    
    def __new__(cls, store: Optional[Any] = None):
        """Factory method that returns a properly configured implementation instance."""
        impl_cls = _build_impl_cls()
        return impl_cls(store)
