"""
Session Store for PraisonAI TUI.

DEPRECATED: This module is deprecated in favor of the core SDK session store.
Use `praisonaiagents.session.DefaultSessionStore` instead, which provides:
- JSON-based persistence (survives restarts)
- File locking for multi-process safety
- Automatic integration with Agent class

This TUI-specific in-memory store is kept for backward compatibility only.
New code should use the core SDK session store.

Example:
    from praisonaiagents.session import get_default_session_store
    store = get_default_session_store()
    store.add_user_message("session-id", "Hello")
    history = store.get_chat_history("session-id")

Maintains chat history in memory for session persistence.
This allows the AI to remember previous messages within a session.
"""

import warnings

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    run_id: Optional[str] = None


@dataclass
class Session:
    """A chat session with history."""
    session_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_message(self, role: str, content: str, run_id: Optional[str] = None) -> None:
        """Add a message to the session."""
        self.messages.append(ChatMessage(
            role=role,
            content=content,
            run_id=run_id,
        ))
        self.updated_at = datetime.now()
    
    def get_history_for_llm(self, max_messages: int = 50) -> List[Dict[str, str]]:
        """
        Get chat history in LLM-compatible format.
        
        Returns list of {"role": "user/assistant", "content": "..."} dicts.
        """
        # Get last N messages
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": msg.role, "content": msg.content} for msg in recent]
    
    @property
    def run_count(self) -> int:
        """Number of user messages (runs) in this session."""
        return sum(1 for msg in self.messages if msg.role == "user")


class SessionStore:
    """
    In-memory session store for TUI.
    
    Maintains chat history across agent runs within a session.
    """
    
    def __init__(self, max_sessions: int = 100, max_messages_per_session: int = 1000):
        """
        Initialize session store.
        
        Args:
            max_sessions: Maximum number of sessions to keep in memory.
            max_messages_per_session: Maximum messages per session.
        """
        self._sessions: Dict[str, Session] = {}
        self._max_sessions = max_sessions
        self._max_messages = max_messages_per_session
    
    def get_or_create_session(self, session_id: str) -> Session:
        """Get existing session or create new one."""
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
            self._cleanup_old_sessions()
            logger.debug(f"Created new session: {session_id}")
        return self._sessions[session_id]
    
    def add_user_message(self, session_id: str, content: str, run_id: Optional[str] = None) -> None:
        """Add a user message to the session."""
        session = self.get_or_create_session(session_id)
        session.add_message("user", content, run_id)
        self._trim_session(session)
        logger.debug(f"Added user message to session {session_id}: {content[:50]}...")
    
    def add_assistant_message(self, session_id: str, content: str, run_id: Optional[str] = None) -> None:
        """Add an assistant message to the session."""
        session = self.get_or_create_session(session_id)
        session.add_message("assistant", content, run_id)
        self._trim_session(session)
        logger.debug(f"Added assistant message to session {session_id}: {content[:50]}...")
    
    def get_chat_history(self, session_id: str, max_messages: int = 50) -> List[Dict[str, str]]:
        """
        Get chat history for a session in LLM-compatible format.
        
        Args:
            session_id: The session ID.
            max_messages: Maximum number of messages to return.
            
        Returns:
            List of {"role": "user/assistant", "content": "..."} dicts.
        """
        if session_id not in self._sessions:
            return []
        return self._sessions[session_id].get_history_for_llm(max_messages)
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(session_id)
    
    def list_sessions(self, limit: int = 50) -> List[Dict]:
        """List all sessions with metadata."""
        sessions = sorted(
            self._sessions.values(),
            key=lambda s: s.updated_at,
            reverse=True
        )[:limit]
        
        return [
            {
                "session_id": s.session_id,
                "created_at": s.created_at.strftime("%Y-%m-%d %H:%M"),
                "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M"),
                "run_count": s.run_count,
            }
            for s in sessions
        ]
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Deleted session: {session_id}")
            return True
        return False
    
    def clear_session(self, session_id: str) -> None:
        """Clear all messages from a session."""
        if session_id in self._sessions:
            self._sessions[session_id].messages.clear()
            self._sessions[session_id].updated_at = datetime.now()
            logger.debug(f"Cleared session: {session_id}")
    
    def _trim_session(self, session: Session) -> None:
        """Trim session to max messages."""
        if len(session.messages) > self._max_messages:
            # Keep the most recent messages
            session.messages = session.messages[-self._max_messages:]
    
    def _cleanup_old_sessions(self) -> None:
        """Remove oldest sessions if over limit."""
        if len(self._sessions) > self._max_sessions:
            # Sort by updated_at and remove oldest
            sorted_sessions = sorted(
                self._sessions.items(),
                key=lambda x: x[1].updated_at
            )
            # Remove oldest sessions
            to_remove = len(self._sessions) - self._max_sessions
            for session_id, _ in sorted_sessions[:to_remove]:
                del self._sessions[session_id]
                logger.debug(f"Removed old session: {session_id}")


# Global session store instance for TUI
_session_store: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Get the global session store instance."""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store
