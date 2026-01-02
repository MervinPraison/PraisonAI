"""
Unified Session for PraisonAI CLI.

Provides persistent session storage shared between TUI and --interactive mode.
Uses JSON-based persistence with file locking for multi-process safety.
"""

import json
import logging
import os
import uuid
import fcntl
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default session directory
DEFAULT_SESSION_DIR = Path.home() / ".praison" / "sessions"


@dataclass
class UnifiedSession:
    """
    Unified session for TUI and --interactive mode.
    
    Stores conversation history, metadata, and token/cost stats.
    Persists to disk automatically.
    """
    session_id: str
    workspace: str = field(default_factory=os.getcwd)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Token and cost tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0
    
    # Model info
    current_model: str = "gpt-4o-mini"
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        self.updated_at = datetime.now().isoformat()
    
    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        self.add_message("user", content)
    
    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message."""
        self.add_message("assistant", content)
    
    def get_chat_history(self, max_messages: int = 50) -> List[Dict[str, str]]:
        """
        Get chat history in LLM-compatible format.
        
        Returns list of {"role": "user/assistant", "content": "..."} dicts.
        """
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [{"role": msg["role"], "content": msg["content"]} for msg in recent]
    
    def update_stats(self, input_tokens: int, output_tokens: int, cost: float = 0.0) -> None:
        """Update token and cost statistics."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost += cost
        self.request_count += 1
        self.updated_at = datetime.now().isoformat()
    
    def clear_messages(self) -> None:
        """Clear all messages from the session."""
        self.messages.clear()
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSession":
        """Create session from dictionary."""
        return cls(**data)
    
    @property
    def message_count(self) -> int:
        """Number of messages in the session."""
        return len(self.messages)
    
    @property
    def user_message_count(self) -> int:
        """Number of user messages in the session."""
        return sum(1 for msg in self.messages if msg.get("role") == "user")


class UnifiedSessionStore:
    """
    Persistent session store with file locking.
    
    Stores sessions as JSON files in ~/.praison/sessions/
    """
    
    def __init__(self, session_dir: Optional[Path] = None):
        """
        Initialize session store.
        
        Args:
            session_dir: Directory to store sessions. Defaults to ~/.praison/sessions/
        """
        self.session_dir = session_dir or DEFAULT_SESSION_DIR
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, UnifiedSession] = {}
        self._last_session_id: Optional[str] = None
    
    def _get_session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.session_dir / f"{session_id}.json"
    
    def _get_last_session_path(self) -> Path:
        """Get the path to the last session marker file."""
        return self.session_dir / ".last_session"
    
    def save(self, session: UnifiedSession) -> None:
        """
        Save a session to disk with file locking.
        
        Args:
            session: Session to save
        """
        path = self._get_session_path(session.session_id)
        session.updated_at = datetime.now().isoformat()
        
        try:
            with open(path, 'w') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(session.to_dict(), f, indent=2)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            # Update cache
            self._cache[session.session_id] = session
            
            # Update last session marker
            self._update_last_session(session.session_id)
            
            logger.debug(f"Saved session: {session.session_id}")
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            raise
    
    def load(self, session_id: str) -> Optional[UnifiedSession]:
        """
        Load a session from disk.
        
        Args:
            session_id: Session ID to load
            
        Returns:
            Session if found, None otherwise
        """
        # Check cache first
        if session_id in self._cache:
            return self._cache[session_id]
        
        path = self._get_session_path(session_id)
        if not path.exists():
            return None
        
        try:
            with open(path, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            
            session = UnifiedSession.from_dict(data)
            self._cache[session_id] = session
            logger.debug(f"Loaded session: {session_id}")
            return session
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
    
    def get_or_create(self, session_id: Optional[str] = None) -> UnifiedSession:
        """
        Get existing session or create new one.
        
        Args:
            session_id: Optional session ID. If None, creates new session.
            
        Returns:
            Session instance
        """
        if session_id:
            session = self.load(session_id)
            if session:
                return session
        
        # Create new session
        new_id = session_id or str(uuid.uuid4())[:8]
        session = UnifiedSession(session_id=new_id)
        self.save(session)
        return session
    
    def delete(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        path = self._get_session_path(session_id)
        if path.exists():
            path.unlink()
            self._cache.pop(session_id, None)
            logger.debug(f"Deleted session: {session_id}")
            return True
        return False
    
    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        List all sessions with metadata.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of session metadata dicts
        """
        sessions = []
        for path in self.session_dir.glob("*.json"):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                sessions.append({
                    "session_id": data.get("session_id"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "message_count": len(data.get("messages", [])),
                    "workspace": data.get("workspace"),
                })
            except Exception as e:
                logger.warning(f"Failed to read session {path}: {e}")
        
        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions[:limit]
    
    def _update_last_session(self, session_id: str) -> None:
        """Update the last session marker."""
        try:
            path = self._get_last_session_path()
            with open(path, 'w') as f:
                f.write(session_id)
            self._last_session_id = session_id
        except Exception as e:
            logger.warning(f"Failed to update last session marker: {e}")
    
    def get_last_session_id(self) -> Optional[str]:
        """Get the ID of the last used session."""
        if self._last_session_id:
            return self._last_session_id
        
        path = self._get_last_session_path()
        if path.exists():
            try:
                self._last_session_id = path.read_text().strip()
                return self._last_session_id
            except Exception as e:
                logger.warning(f"Failed to read last session marker: {e}")
        return None
    
    def get_last_session(self) -> Optional[UnifiedSession]:
        """Get the last used session."""
        session_id = self.get_last_session_id()
        if session_id:
            return self.load(session_id)
        return None


# Global session store instance
_session_store: Optional[UnifiedSessionStore] = None


def get_session_store() -> UnifiedSessionStore:
    """Get the global session store instance."""
    global _session_store
    if _session_store is None:
        _session_store = UnifiedSessionStore()
    return _session_store
