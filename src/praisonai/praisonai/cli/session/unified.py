"""
Unified Session for PraisonAI CLI.

Provides persistent session storage shared between TUI and --interactive mode.
Uses JSON-based persistence with file locking for multi-process safety.
"""

import json
import logging
import os
import sys
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# fcntl is Unix-only; on Windows, use msvcrt for file locking
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

logger = logging.getLogger(__name__)

# Module-level sentinel to track if we've warned about degraded locking
_WARNED_NO_FCNTL = False

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
    
    # Track baseline values for proper delta merging (not persisted)
    _baseline_input_tokens: int = field(default=0, init=False, repr=False)
    _baseline_output_tokens: int = field(default=0, init=False, repr=False) 
    _baseline_cost: float = field(default=0.0, init=False, repr=False)
    _baseline_request_count: int = field(default=0, init=False, repr=False)
    
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
    
    def set_baseline_stats(self) -> None:
        """Set baseline stats for delta tracking during merge operations."""
        self._baseline_input_tokens = self.total_input_tokens
        self._baseline_output_tokens = self.total_output_tokens
        self._baseline_cost = self.total_cost
        self._baseline_request_count = self.request_count
        
    def get_stat_deltas(self) -> Dict[str, int | float]:
        """Get deltas from baseline for proper merge."""
        return {
            "input_tokens": self.total_input_tokens - self._baseline_input_tokens,
            "output_tokens": self.total_output_tokens - self._baseline_output_tokens,
            "cost": self.total_cost - self._baseline_cost,
            "request_count": self.request_count - self._baseline_request_count,
        }
    
    def clear_messages(self) -> None:
        """Clear all messages from the session."""
        self.messages.clear()
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary, excluding internal baseline fields."""
        data = asdict(self)
        # Remove internal baseline fields from serialization
        for key in list(data.keys()):
            if key.startswith('_baseline_'):
                del data[key]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnifiedSession":
        """Create session from dictionary."""
        # Remove any internal baseline fields that might have leaked into saved data
        clean_data = {k: v for k, v in data.items() if not k.startswith('_baseline_')}
        instance = cls(**clean_data)
        # Initialize baseline values to current values
        instance.set_baseline_stats()
        return instance
    
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
        self.session_dir = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, UnifiedSession] = {}
        self._cache_mtime: Dict[str, float] = {}
        self._lock = threading.RLock()
        self._last_session_id: Optional[str] = None

    @staticmethod
    def _message_key(message: Dict[str, Any]) -> Tuple[Any, ...]:
        return (
            message.get("role"),
            message.get("content"),
            message.get("timestamp"),
        )

    
    def _get_session_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        return self.session_dir / f"{session_id}.json"
    
    def _get_last_session_path(self) -> Path:
        """Get the path to the last session marker file."""
        return self.session_dir / ".last_session"

    @staticmethod
    def _messages_common_prefix(
        left: List[Dict[str, str]], right: List[Dict[str, str]]
    ) -> int:
        """Return shared message prefix length for safe concurrent merge."""
        prefix = 0
        for left_msg, right_msg in zip(left, right, strict=False):
            if left_msg.get("role") != right_msg.get("role"):
                break
            if left_msg.get("content") != right_msg.get("content"):
                break
            prefix += 1
        return prefix

    def _parse_session_file(self, f) -> Optional[UnifiedSession]:
        """Parse session JSON from an open file handle."""
        try:
            f.seek(0)
            raw = f.read()
            if not raw:
                return None
            data = json.loads(raw.decode('utf-8'))
            return UnifiedSession.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to parse session file: {e}")
            return None

    def _read_session_from_file(self, path: Path) -> Optional[UnifiedSession]:
        """Read a session from disk without using the in-process cache."""
        if not path.exists():
            return None

        try:
            with open(path, 'rb') as f:
                if sys.platform == "win32":
                    import msvcrt
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_RLCK, 1)
                    try:
                        session = self._parse_session_file(f)
                    finally:
                        f.seek(0)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                elif _HAS_FCNTL:
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                    try:
                        session = self._parse_session_file(f)
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                else:
                    session = self._parse_session_file(f)

            return session
        except Exception as e:
            logger.error(f"Failed to read session file {path}: {e}")
            return None

    def _merge_sessions(
        self, disk_session: Optional[UnifiedSession], incoming: UnifiedSession
    ) -> UnifiedSession:
        """Merge incoming session updates without clobbering concurrent writes."""
        if disk_session is None:
            return incoming

        merged = UnifiedSession.from_dict(disk_session.to_dict())
        
        # Use prefix-based merge for append-only scenarios (original design)
        prefix = self._messages_common_prefix(disk_session.messages, incoming.messages)
        merged.messages = disk_session.messages + incoming.messages[prefix:]

        # Merge stats using deltas instead of max()
        incoming_deltas = incoming.get_stat_deltas()
        merged.total_input_tokens += max(0, incoming_deltas["input_tokens"])
        merged.total_output_tokens += max(0, incoming_deltas["output_tokens"])
        merged.total_cost += max(0.0, incoming_deltas["cost"])
        merged.request_count += max(0, incoming_deltas["request_count"])
        
        # Update other fields with incoming values if present
        if incoming.current_model:
            merged.current_model = incoming.current_model
        if incoming.metadata:
            merged.metadata.update(incoming.metadata)
        if incoming.workspace:
            merged.workspace = incoming.workspace

        return merged
    
    def _acquire_exclusive_lock(self, file_obj) -> None:
        if sys.platform == "win32":
            import msvcrt
            file_obj.seek(0)
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_LOCK, 1)
        elif _HAS_FCNTL:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
        else:
            global _WARNED_NO_FCNTL
            if not _WARNED_NO_FCNTL:
                logger.warning(
                    "File locking unavailable on this platform (fcntl not available); "
                    "concurrent writers may corrupt session files."
                )
                _WARNED_NO_FCNTL = True

    def _release_exclusive_lock(self, file_obj) -> None:
        if sys.platform == "win32":
            import msvcrt
            file_obj.seek(0)
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
        elif _HAS_FCNTL:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)

    def _read_json_locked(self, file_obj) -> Optional[Dict[str, Any]]:
        """Read session JSON (caller must hold exclusive lock)."""
        file_obj.seek(0)
        raw = file_obj.read().decode("utf-8")
        if not raw.strip():
            return None
        return json.loads(raw)

    def _write_json_locked(self, file_obj, data: Dict[str, Any]) -> None:
        """Write session JSON (caller must hold exclusive lock)."""
        json_data = json.dumps(data, indent=2).encode("utf-8")
        file_obj.seek(0)
        file_obj.truncate()
        file_obj.write(json_data)
        file_obj.flush()
        os.fsync(file_obj.fileno())


    def save(self, session: UnifiedSession) -> None:
        """
        Save a session to disk with file locking.
        
        Args:
            session: Session to save
        """
        path = self._get_session_path(session.session_id)
        
        try:
            if not path.exists():
                path.touch()

            # Set baseline stats for proper delta tracking
            session.set_baseline_stats()
            
            to_save = session
            with open(path, "r+b") as f:
                self._acquire_exclusive_lock(f)
                try:
                    existing_data = self._read_json_locked(f)
                    if existing_data:
                        on_disk = UnifiedSession.from_dict(existing_data)
                        to_save = self._merge_sessions(on_disk, session)
                    to_save.updated_at = datetime.now().isoformat()
                    self._write_json_locked(f, to_save.to_dict())
                finally:
                    self._release_exclusive_lock(f)

            # Safely update mtime cache with error handling
            try:
                mtime = path.stat().st_mtime
            except (FileNotFoundError, OSError):
                # File was deleted/moved between write and stat, skip mtime update
                mtime = datetime.now().timestamp()

            with self._lock:
                self._cache[session.session_id] = to_save
                self._cache_mtime[session.session_id] = mtime

            # Update last session marker
            self._update_last_session(session.session_id)
            logger.debug(f"Saved session: {session.session_id}")
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id}: {e}")
            raise
    
    def _is_cache_fresh(self, session_id: str, path: Path) -> bool:
        """Return True if in-memory cache matches the on-disk file."""
        if session_id not in self._cache:
            return False
        if not path.exists():
            return False
        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return False
        cached_mtime = self._cache_mtime.get(session_id, 0)
        return current_mtime <= cached_mtime

    def load(self, session_id: str) -> Optional[UnifiedSession]:
        """
        Load a session from disk.
        
        Args:
            session_id: Session ID to load
            
        Returns:
            Session if found, None otherwise
        """
        path = self._get_session_path(session_id)
        if not path.exists():
            with self._lock:
                self._cache.pop(session_id, None)
                self._cache_mtime.pop(session_id, None)
            return None

        with self._lock:
            if self._is_cache_fresh(session_id, path):
                return self._cache[session_id]
        
        try:
            with open(path, "r+b") as f:
                self._acquire_exclusive_lock(f)
                try:
                    data = self._read_json_locked(f)
                finally:
                    self._release_exclusive_lock(f)
            if data is None:
                return None

            session = UnifiedSession.from_dict(data)
            # Set baseline stats for proper delta tracking
            session.set_baseline_stats()
            
            try:
                mtime = path.stat().st_mtime
            except (FileNotFoundError, OSError):
                # File was deleted/moved after read, skip mtime update
                mtime = datetime.now().timestamp()

            with self._lock:
                self._cache[session_id] = session
                self._cache_mtime[session_id] = mtime
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
        # Set baseline stats for new session
        session.set_baseline_stats()
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
            path.unlink(missing_ok=True)
            with self._lock:
                self._cache.pop(session_id, None)
                self._cache_mtime.pop(session_id, None)
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
