"""
Default Session Store for PraisonAI Agents.

JSON-based session persistence with file locking and atomic writes.
Zero dependencies beyond stdlib.
"""

import fcntl
import json
import logging
import os
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Default session directory
DEFAULT_SESSION_DIR = os.path.expanduser("~/.praison/sessions")

# Default limits
DEFAULT_MAX_MESSAGES = 100
DEFAULT_LOCK_TIMEOUT = 5.0  # seconds


@dataclass
class SessionMessage:
    """A single message in a session."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMessage":
        """Create from dictionary."""
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SessionData:
    """Complete session data structure."""
    session_id: str
    messages: List[SessionMessage] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_name: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "agent_name": self.agent_name,
            "user_id": self.user_id,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        """Create from dictionary."""
        messages = [
            SessionMessage.from_dict(m) 
            for m in data.get("messages", [])
        ]
        return cls(
            session_id=data.get("session_id", ""),
            messages=messages,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            agent_name=data.get("agent_name"),
            user_id=data.get("user_id"),
            metadata=data.get("metadata", {}),
        )
    
    def get_chat_history(self, max_messages: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Get chat history in LLM-compatible format.
        
        Returns list of {"role": "user/assistant", "content": "..."} dicts.
        """
        messages = self.messages
        if max_messages and len(messages) > max_messages:
            messages = messages[-max_messages:]
        return [{"role": m.role, "content": m.content} for m in messages]


class FileLock:
    """
    Cross-platform file locking.
    
    Uses fcntl on Unix and msvcrt on Windows.
    """
    
    def __init__(self, filepath: str, timeout: float = DEFAULT_LOCK_TIMEOUT):
        self.filepath = filepath
        self.timeout = timeout
        self._lock_file = None
        self._lock_path = filepath + ".lock"
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
    
    def acquire(self) -> bool:
        """Acquire the file lock."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self._lock_path) or ".", exist_ok=True)
        
        start_time = time.time()
        while True:
            try:
                self._lock_file = open(self._lock_path, "w")
                if sys.platform == "win32":
                    # Windows locking
                    import msvcrt
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    # Unix locking
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError, BlockingIOError):
                if self._lock_file:
                    self._lock_file.close()
                    self._lock_file = None
                
                if time.time() - start_time > self.timeout:
                    logger.warning(f"Failed to acquire lock for {self.filepath} after {self.timeout}s")
                    return False
                
                time.sleep(0.05)  # Wait 50ms before retry
    
    def release(self) -> None:
        """Release the file lock."""
        if self._lock_file:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            except (IOError, OSError):
                pass
            finally:
                self._lock_file.close()
                self._lock_file = None
                # Note: We don't remove the lock file to avoid race conditions
                # where another process has opened but not yet locked the file


class DefaultSessionStore:
    """
    JSON-based session persistence with file locking.
    
    Features:
    - Zero configuration required
    - Automatic file locking for multi-process safety
    - Atomic writes to prevent corruption
    - Configurable message limits
    - Thread-safe operations
    
    Usage:
        store = DefaultSessionStore()
        
        # Add messages
        store.add_message("session-123", "user", "Hello")
        store.add_message("session-123", "assistant", "Hi there!")
        
        # Get history
        history = store.get_chat_history("session-123")
        # [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]
        
        # Restore in new process
        store2 = DefaultSessionStore()
        history = store2.get_chat_history("session-123")  # Same history!
    """
    
    def __init__(
        self,
        session_dir: Optional[str] = None,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    ):
        """
        Initialize session store.
        
        Args:
            session_dir: Directory for session files. Defaults to ~/.praison/sessions/
            max_messages: Maximum messages to keep per session.
            lock_timeout: Timeout for file lock acquisition.
        """
        self.session_dir = session_dir or DEFAULT_SESSION_DIR
        self.max_messages = max_messages
        self.lock_timeout = lock_timeout
        self._lock = threading.RLock()
        self._cache: Dict[str, SessionData] = {}
        
        # Ensure session directory exists
        os.makedirs(self.session_dir, exist_ok=True)
    
    def _get_session_path(self, session_id: str) -> str:
        """Get the file path for a session."""
        # Sanitize session_id for filesystem
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
        return os.path.join(self.session_dir, f"{safe_id}.json")
    
    def _load_session(self, session_id: str) -> SessionData:
        """Load session from disk with file locking."""
        filepath = self._get_session_path(session_id)
        
        # Check cache first
        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id]
        
        # Load from disk
        if not os.path.exists(filepath):
            session = SessionData(session_id=session_id)
            with self._lock:
                self._cache[session_id] = session
            return session
        
        with FileLock(filepath, self.lock_timeout):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session = SessionData.from_dict(data)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load session {session_id}: {e}")
                session = SessionData(session_id=session_id)
        
        with self._lock:
            self._cache[session_id] = session
        
        return session
    
    def _save_session(self, session: SessionData) -> bool:
        """Save session to disk with atomic write."""
        filepath = self._get_session_path(session.session_id)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        
        # Trim messages if over limit
        if len(session.messages) > self.max_messages:
            session.messages = session.messages[-self.max_messages:]
        
        with FileLock(filepath, self.lock_timeout):
            try:
                # Atomic write: write to temp file, then rename
                dir_path = os.path.dirname(filepath)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=dir_path,
                    delete=False,
                    suffix=".tmp"
                ) as f:
                    json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
                    temp_path = f.name
                
                # Atomic rename
                os.replace(temp_path, filepath)
                return True
            except (IOError, OSError) as e:
                logger.error(f"Failed to save session {session.session_id}: {e}")
                # Clean up temp file if it exists
                try:
                    if 'temp_path' in locals():
                        os.remove(temp_path)
                except (IOError, OSError):
                    pass
                return False
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add a message to a session.
        
        Args:
            session_id: The session ID.
            role: Message role ("user", "assistant", "system").
            content: Message content.
            metadata: Optional metadata.
            
        Returns:
            True if saved successfully.
        """
        filepath = self._get_session_path(session_id)
        
        message = SessionMessage(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        
        # Use file lock for atomic read-modify-write
        with FileLock(filepath, self.lock_timeout):
            # Always reload from disk inside lock to avoid race conditions
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session = SessionData.from_dict(data)
                except (json.JSONDecodeError, IOError):
                    session = SessionData(session_id=session_id)
            else:
                session = SessionData(session_id=session_id)
            
            # Add message
            session.messages.append(message)
            session.updated_at = datetime.now(timezone.utc).isoformat()
            
            # Trim messages if over limit
            if len(session.messages) > self.max_messages:
                session.messages = session.messages[-self.max_messages:]
            
            # Write atomically
            try:
                dir_path = os.path.dirname(filepath) or "."
                os.makedirs(dir_path, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=dir_path,
                    delete=False,
                    suffix=".tmp"
                ) as f:
                    json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
                    temp_path = f.name
                
                os.replace(temp_path, filepath)
                
                # Update cache
                with self._lock:
                    self._cache[session_id] = session
                
                return True
            except (IOError, OSError) as e:
                logger.error(f"Failed to save session {session_id}: {e}")
                try:
                    if 'temp_path' in locals():
                        os.remove(temp_path)
                except (IOError, OSError):
                    pass
                return False
    
    def add_user_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a user message to a session."""
        return self.add_message(session_id, "user", content, metadata)
    
    def add_assistant_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add an assistant message to a session."""
        return self.add_message(session_id, "assistant", content, metadata)
    
    def get_chat_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Get chat history for a session in LLM-compatible format.
        
        Args:
            session_id: The session ID.
            max_messages: Maximum messages to return (defaults to store limit).
            
        Returns:
            List of {"role": "user/assistant", "content": "..."} dicts.
        """
        session = self._load_session(session_id)
        limit = max_messages or self.max_messages
        return session.get_chat_history(limit)
    
    def get_session(self, session_id: str) -> SessionData:
        """Get full session data."""
        return self._load_session(session_id)
    
    def set_agent_info(
        self,
        session_id: str,
        agent_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Set agent info for a session."""
        session = self._load_session(session_id)
        
        with self._lock:
            if agent_name:
                session.agent_name = agent_name
            if user_id:
                session.user_id = user_id
            self._cache[session_id] = session
        
        return self._save_session(session)
    
    def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session."""
        session = self._load_session(session_id)
        
        with self._lock:
            session.messages.clear()
            self._cache[session_id] = session
        
        return self._save_session(session)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session completely."""
        filepath = self._get_session_path(session_id)
        
        with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
        
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List all sessions with metadata."""
        sessions = []
        
        try:
            for filename in os.listdir(self.session_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.session_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        sessions.append({
                            "session_id": data.get("session_id", filename[:-5]),
                            "agent_name": data.get("agent_name"),
                            "created_at": data.get("created_at"),
                            "updated_at": data.get("updated_at"),
                            "message_count": len(data.get("messages", [])),
                        })
                    except (json.JSONDecodeError, IOError):
                        continue
        except (IOError, OSError):
            pass
        
        # Sort by updated_at descending
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return sessions[:limit]
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        filepath = self._get_session_path(session_id)
        return os.path.exists(filepath)
    
    def invalidate_cache(self, session_id: Optional[str] = None) -> None:
        """Invalidate cache for a session or all sessions."""
        with self._lock:
            if session_id:
                self._cache.pop(session_id, None)
            else:
                self._cache.clear()


# Global session store instance (lazy initialized)
_default_store: Optional[DefaultSessionStore] = None
_store_lock = threading.Lock()


def get_default_session_store() -> DefaultSessionStore:
    """Get the global default session store instance."""
    global _default_store
    
    if _default_store is None:
        with _store_lock:
            if _default_store is None:
                _default_store = DefaultSessionStore()
    
    return _default_store
