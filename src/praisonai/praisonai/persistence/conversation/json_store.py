"""
JSON file-based implementation of ConversationStore.

Simple file-based storage for development and testing.
No external dependencies required.
"""

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional
import threading

from .base import ConversationStore, ConversationSession, ConversationMessage

logger = logging.getLogger(__name__)

# Reject ids that could escape the storage dir (path separators, ``..``) before
# interpolating them into a filename. External ids reach here via
# api/agent_invoke -> PraisonAIDB -> JSONConversationStore.
_ID_RE = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")

# The store keeps its own index at ``_sessions_index.json``; a session id that
# maps to the same file would let create/update silently overwrite the index
# (and vice versa), corrupting every session's listing. Reserve it.
_RESERVED_IDS = frozenset({"_sessions_index"})


def _validate_id(session_id: str) -> str:
    """Reject a session id that is unsafe as a filesystem path component."""
    if (
        not isinstance(session_id, str)
        or ".." in session_id
        or session_id in _RESERVED_IDS
        or not _ID_RE.match(session_id)
    ):
        raise ValueError(f"invalid session id for filesystem storage: {session_id!r}")
    return session_id


def _atomic_write_json(path: Path, payload, pretty: bool = True) -> None:
    """Write JSON to ``path`` atomically (temp file + os.replace).

    A crash / Ctrl-C mid-write can never leave the file empty or truncated,
    which would otherwise silently zero a session's conversation history on the
    next load.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".conv-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            if pretty:
                json.dump(payload, f, indent=2, default=str)
            else:
                json.dump(payload, f, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class JSONConversationStore(ConversationStore):
    """
    JSON file-based conversation store.
    
    Stores sessions and messages in JSON files.
    Suitable for development, testing, and small-scale deployments.
    
    Example:
        store = JSONConversationStore(path="./data/conversations")
    """
    
    def __init__(
        self,
        path: str = "./praisonai_conversations",
        pretty: bool = True,
    ):
        """
        Initialize JSON conversation store.
        
        Args:
            path: Directory path for JSON files
            pretty: Use pretty-printed JSON (default: True)
        """
        self.path = Path(path)
        self.pretty = pretty
        self._lock = threading.Lock()
        
        # Create directory if it doesn't exist
        self.path.mkdir(parents=True, exist_ok=True)
        
        # Sessions index file
        self._index_file = self.path / "_sessions_index.json"
        self._load_index()
    
    def _load_index(self):
        """Load or create sessions index."""
        if self._index_file.exists():
            with open(self._index_file, 'r') as f:
                self._index = json.load(f)
        else:
            self._index = {"sessions": {}}
            self._save_index()
    
    def _save_index(self):
        """Save sessions index atomically."""
        _atomic_write_json(self._index_file, self._index, self.pretty)
    
    def _session_file(self, session_id: str) -> Path:
        """Get path to session file (validated against traversal)."""
        return self.path / f"{_validate_id(session_id)}.json"
    
    def _load_session_data(self, session_id: str) -> Optional[Dict]:
        """Load session data from file."""
        file_path = self._session_file(session_id)
        if file_path.exists():
            with open(file_path, 'r') as f:
                return json.load(f)
        return None
    
    def _save_session_data(self, session_id: str, data: Dict):
        """Save session data to file atomically."""
        file_path = self._session_file(session_id)
        _atomic_write_json(file_path, data, self.pretty)
    
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        with self._lock:
            data = {
                "session": session.to_dict(),
                "messages": []
            }
            self._save_session_data(session.session_id, data)
            
            # Update index
            self._index["sessions"][session.session_id] = {
                "user_id": session.user_id,
                "agent_id": session.agent_id,
                "name": session.name,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
            }
            self._save_index()
            
            return session
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        data = self._load_session_data(session_id)
        if data and "session" in data:
            return ConversationSession.from_dict(data["session"])
        return None
    
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        with self._lock:
            data = self._load_session_data(session.session_id)
            if not data:
                raise ValueError(f"Session {session.session_id} not found")
            
            session.updated_at = time.time()
            data["session"] = session.to_dict()
            self._save_session_data(session.session_id, data)
            
            # Update index
            self._index["sessions"][session.session_id].update({
                "name": session.name,
                "updated_at": session.updated_at,
            })
            self._save_index()
            
            return session
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        with self._lock:
            file_path = self._session_file(session_id)
            if file_path.exists():
                file_path.unlink()
                
                # Update index
                if session_id in self._index["sessions"]:
                    del self._index["sessions"][session_id]
                    self._save_index()
                
                return True
            return False
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """List sessions, optionally filtered by user or agent."""
        sessions = []
        
        for sid, info in self._index["sessions"].items():
            if user_id and info.get("user_id") != user_id:
                continue
            if agent_id and info.get("agent_id") != agent_id:
                continue
            
            session = self.get_session(sid)
            if session:
                sessions.append(session)
        
        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        
        return sessions[offset:offset + limit]
    
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a session."""
        with self._lock:
            data = self._load_session_data(session_id)
            if not data:
                raise ValueError(f"Session {session_id} not found")
            
            message.session_id = session_id
            data["messages"].append(message.to_dict())
            
            # Update session timestamp
            data["session"]["updated_at"] = time.time()
            
            self._save_session_data(session_id, data)
            
            # Update index
            if session_id in self._index["sessions"]:
                self._index["sessions"][session_id]["updated_at"] = time.time()
                self._save_index()
            
            return message
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Get messages from a session."""
        data = self._load_session_data(session_id)
        if not data:
            return []
        
        messages = [ConversationMessage.from_dict(m) for m in data.get("messages", [])]
        
        # Apply filters
        if before:
            messages = [m for m in messages if m.created_at < before]
        if after:
            messages = [m for m in messages if m.created_at > after]
        
        # Sort by created_at
        messages.sort(key=lambda m: m.created_at)
        
        if limit:
            messages = messages[-limit:]
        
        return messages
    
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages. If message_ids is None, delete all messages in session."""
        with self._lock:
            data = self._load_session_data(session_id)
            if not data:
                return 0
            
            if message_ids is None:
                count = len(data["messages"])
                data["messages"] = []
            else:
                original_count = len(data["messages"])
                data["messages"] = [m for m in data["messages"] if m.get("id") not in message_ids]
                count = original_count - len(data["messages"])
            
            self._save_session_data(session_id, data)
            return count
    
    def close(self) -> None:
        """Close the store."""
        pass  # No resources to release
