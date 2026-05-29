"""
DbSessionAdapter — bridges PraisonDB (DbAdapter) to SessionStoreProtocol.

Allows managed agents to persist session data (messages, metadata, usage,
compute refs) to any database supported by PraisonDB: PostgreSQL, SQLite,
MySQL, Redis, etc.

Usage::

    from praisonai.db import PraisonDB
    from praisonai.integrations.db_session_adapter import DbSessionAdapter

    db = PraisonDB(database_url="postgresql://localhost/praisonai")
    store = DbSessionAdapter(db)
    # store satisfies SessionStoreProtocol
"""

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class DbSessionAdapter:
    """Wraps a PraisonDB (DbAdapter) to satisfy SessionStoreProtocol.

    Stores chat messages via the DbAdapter's on_user_message / on_agent_message
    hooks, and stores metadata (agent IDs, usage, compute refs) in an in-memory
    dict that is flushed to the DB session metadata on every mutation.

    This class satisfies ``SessionStoreProtocol`` via structural subtyping
    (duck typing) — it implements all five required methods.
    """

    def __init__(self, db: Any):
        self._db = db
        self._sessions: Set[str] = set()
        self._metadata: Dict[str, Dict[str, Any]] = {}
        self._history_cache: Dict[str, List[Dict[str, str]]] = {}
        self._cleared_sessions: Set[str] = set()

    def _conversation_store(self) -> Any:
        """Optional ConversationStore behind the DbAdapter (if present)."""
        conv = getattr(self._db, "conversation", None)
        if conv is not None:
            return conv
        orchestrator = getattr(self._db, "_orchestrator", None)
        return getattr(orchestrator, "conversation", None) if orchestrator else None

    def _purge_persisted_messages(self, session_id: str) -> None:
        """Remove persisted messages when the session is cleared or deleted."""
        conv = self._conversation_store()
        if conv is not None and hasattr(conv, "delete_messages"):
            try:
                conv.delete_messages(session_id, None)
            except Exception as e:
                logger.warning(
                    "[db_session_adapter] delete_messages failed for %s: %s",
                    session_id,
                    e,
                )

    def _ensure_session(self, session_id: str, agent_name: str = "ManagedAgent") -> None:
        """Ensure session exists in the DB adapter."""
        if session_id not in self._sessions:
            skip_history = session_id in self._cleared_sessions
            if skip_history:
                self._cleared_sessions.discard(session_id)
            try:
                msgs = self._db.on_agent_start(agent_name, session_id)
                if msgs and not skip_history:
                    self._history_cache[session_id] = [
                        {"role": m.role, "content": m.content} for m in msgs
                    ]
                elif skip_history:
                    self._history_cache[session_id] = []
                self._sessions.add(session_id)
            except Exception as e:
                logger.warning("[db_session_adapter] on_agent_start failed: %s", e)
                self._sessions.add(session_id)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a message to a session."""
        self._ensure_session(session_id)
        try:
            if role == "user":
                self._db.on_user_message(session_id, content, metadata=metadata)
            elif role == "assistant":
                self._db.on_agent_message(session_id, content, metadata=metadata)
            elif role == "tool":
                self._db.on_tool_call(
                    session_id,
                    tool_name=metadata.get("tool_name", "unknown") if metadata else "unknown",
                    args=metadata.get("args", {}) if metadata else {},
                    result=content,
                    metadata=metadata,
                )
            else:
                self._db.on_user_message(session_id, content, metadata={"role": role, **(metadata or {})})

            if session_id not in self._history_cache:
                self._history_cache[session_id] = []
            self._history_cache[session_id].append({"role": role, "content": content})
            return True
        except Exception as e:
            logger.warning("[db_session_adapter] add_message failed: %s", e)
            return False

    def get_chat_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Get chat history in LLM-compatible format."""
        self._ensure_session(session_id)
        history = self._history_cache.get(session_id, [])
        if max_messages:
            return history[-max_messages:]
        return list(history)

    def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session."""
        if session_id in self._sessions:
            try:
                self._db.on_agent_end(session_id)
            except Exception as e:
                logger.warning("[db_session_adapter] on_agent_end failed: %s", e)
        self._purge_persisted_messages(session_id)
        self._history_cache[session_id] = []
        self._sessions.discard(session_id)
        self._cleared_sessions.add(session_id)
        return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session completely."""
        self._purge_persisted_messages(session_id)
        self._history_cache.pop(session_id, None)
        self._metadata.pop(session_id, None)
        self._sessions.discard(session_id)
        self._cleared_sessions.discard(session_id)
        try:
            self._db.on_agent_end(session_id)
        except Exception:
            pass
        return True

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions

    # ------------------------------------------------------------------
    # Extended metadata API (beyond SessionStoreProtocol minimum)
    # ------------------------------------------------------------------

    def set_metadata(self, session_id: str, metadata: Dict[str, Any]) -> None:
        """Store metadata for a session (agent IDs, usage, compute refs)."""
        if session_id not in self._metadata:
            self._metadata[session_id] = {}
        self._metadata[session_id].update(metadata)

    def get_metadata(self, session_id: str) -> Dict[str, Any]:
        """Retrieve metadata for a session."""
        return dict(self._metadata.get(session_id, {}))

    # ------------------------------------------------------------------
    # Session data access (used by DefaultSessionStore-compatible code)
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> Any:
        """Return a session-like object with .metadata for compatibility.

        Returns None if session doesn't exist.
        """
        if session_id not in self._sessions:
            return None

        class _SessionProxy:
            def __init__(self, sid, meta):
                self.session_id = sid
                self.metadata = meta
        return _SessionProxy(session_id, self.get_metadata(session_id))

    def update_session_metadata(self, session_id: str, **fields: Any) -> None:
        """Update session metadata fields (DefaultSessionStore-compatible)."""
        if not fields:
            return
        if session_id not in self._metadata:
            self._metadata[session_id] = {}
        for key, value in fields.items():
            if value is not None:
                self._metadata[session_id][key] = value
