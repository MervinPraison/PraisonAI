"""
Session Hierarchy for PraisonAI Agents.

Extends the session system with parent-child relationships,
forking, and revert capabilities.
"""

import copy
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .store import SessionData, SessionMessage, DefaultSessionStore, FileLock

logger = logging.getLogger(__name__)


@dataclass
class SessionSnapshot:
    """A snapshot of session state at a point in time."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    message_index: int = 0  # Index of last message in snapshot
    created_at: float = field(default_factory=time.time)
    label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "message_index": self.message_index,
            "created_at": self.created_at,
            "label": self.label,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSnapshot":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            session_id=data.get("session_id", ""),
            message_index=data.get("message_index", 0),
            created_at=data.get("created_at", time.time()),
            label=data.get("label"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ExtendedSessionData(SessionData):
    """Extended session data with hierarchy support."""
    
    parent_id: Optional[str] = None
    forked_from_message_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    snapshots: List[SessionSnapshot] = field(default_factory=list)
    is_shared: bool = False
    title: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "parent_id": self.parent_id,
            "forked_from_message_id": self.forked_from_message_id,
            "children_ids": self.children_ids,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "is_shared": self.is_shared,
            "title": self.title,
        })
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtendedSessionData":
        messages = [
            SessionMessage.from_dict(m) 
            for m in data.get("messages", [])
        ]
        snapshots = [
            SessionSnapshot.from_dict(s)
            for s in data.get("snapshots", [])
        ]
        return cls(
            session_id=data.get("session_id", ""),
            messages=messages,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            agent_name=data.get("agent_name"),
            user_id=data.get("user_id"),
            metadata=data.get("metadata", {}),
            parent_id=data.get("parent_id"),
            forked_from_message_id=data.get("forked_from_message_id"),
            children_ids=data.get("children_ids", []),
            snapshots=snapshots,
            is_shared=data.get("is_shared", False),
            title=data.get("title"),
        )
    
    @classmethod
    def from_session_data(cls, session: SessionData) -> "ExtendedSessionData":
        """Convert a basic SessionData to ExtendedSessionData."""
        return cls(
            session_id=session.session_id,
            messages=session.messages,
            created_at=session.created_at,
            updated_at=session.updated_at,
            agent_name=session.agent_name,
            user_id=session.user_id,
            metadata=session.metadata,
        )


class HierarchicalSessionStore(DefaultSessionStore):
    """
    Session store with hierarchy, forking, and revert support.
    
    Extends DefaultSessionStore with:
    - Parent-child session relationships
    - Session forking from any message
    - Snapshot creation and revert
    - Session sharing
    
    Usage:
        store = HierarchicalSessionStore()
        
        # Create parent session
        parent_id = store.create_session(title="Main conversation")
        
        # Fork from a message
        child_id = store.fork_session(parent_id, from_message_index=5)
        
        # Create snapshot
        snapshot_id = store.create_snapshot(parent_id, label="Before refactor")
        
        # Revert to snapshot
        store.revert_to_snapshot(parent_id, snapshot_id)
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._extended_cache: Dict[str, ExtendedSessionData] = {}
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Add a message to a session, preserving extended fields.
        
        Overrides parent to preserve extended session data.
        """
        from .store import SessionMessage
        
        # Load extended session (force reload to get latest)
        session = self._load_extended_session(session_id, force_reload=True)
        
        message = SessionMessage(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        
        session.messages.append(message)
        
        # Trim messages if over limit
        if len(session.messages) > self.max_messages:
            session.messages = session.messages[-self.max_messages:]
        
        return self._save_extended_session(session)
    
    def _load_extended_session(self, session_id: str, force_reload: bool = False) -> ExtendedSessionData:
        """Load extended session from disk."""
        filepath = self._get_session_path(session_id)
        
        # Check cache first (unless force reload)
        if not force_reload:
            with self._lock:
                if session_id in self._extended_cache:
                    return self._extended_cache[session_id]
        
        # Load from disk
        if not os.path.exists(filepath):
            session = ExtendedSessionData(session_id=session_id)
            with self._lock:
                self._extended_cache[session_id] = session
            return session
        
        with FileLock(filepath, self.lock_timeout):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                session = ExtendedSessionData.from_dict(data)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load session {session_id}: {e}")
                session = ExtendedSessionData(session_id=session_id)
        
        with self._lock:
            self._extended_cache[session_id] = session
        
        return session
    
    def _save_extended_session(self, session: ExtendedSessionData) -> bool:
        """Save extended session to disk."""
        filepath = self._get_session_path(session.session_id)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        
        # Trim messages if over limit
        if len(session.messages) > self.max_messages:
            session.messages = session.messages[-self.max_messages:]
        
        with FileLock(filepath, self.lock_timeout):
            try:
                import tempfile
                dir_path = os.path.dirname(filepath)
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
                
                with self._lock:
                    self._extended_cache[session.session_id] = session
                
                return True
            except (IOError, OSError) as e:
                logger.error(f"Failed to save session {session.session_id}: {e}")
                try:
                    if 'temp_path' in locals():
                        os.remove(temp_path)
                except (IOError, OSError):
                    pass
                return False
    
    def create_session(
        self,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        parent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a new session.
        
        Args:
            session_id: Optional custom session ID
            title: Optional session title
            parent_id: Optional parent session ID
            agent_name: Optional agent name
            metadata: Optional metadata
            
        Returns:
            The session ID
        """
        sid = session_id or str(uuid.uuid4())
        
        session = ExtendedSessionData(
            session_id=sid,
            title=title,
            parent_id=parent_id,
            agent_name=agent_name,
            metadata=metadata or {},
        )
        
        # Update parent's children list
        if parent_id:
            parent = self._load_extended_session(parent_id)
            if sid not in parent.children_ids:
                parent.children_ids.append(sid)
                self._save_extended_session(parent)
        
        self._save_extended_session(session)
        return sid
    
    def fork_session(
        self,
        session_id: str,
        from_message_index: Optional[int] = None,
        title: Optional[str] = None,
    ) -> str:
        """
        Fork a session from a specific message.
        
        Args:
            session_id: The session to fork from
            from_message_index: Message index to fork from (None = all messages)
            title: Optional title for the forked session
            
        Returns:
            The new forked session ID
        """
        # Force reload to get latest messages from disk
        parent = self._load_extended_session(session_id, force_reload=True)
        
        # Determine which messages to copy
        if from_message_index is None:
            messages_to_copy = copy.deepcopy(parent.messages)
            fork_msg_id = None
        else:
            messages_to_copy = copy.deepcopy(parent.messages[:from_message_index + 1])
            fork_msg_id = str(from_message_index)
        
        # Create new session
        new_id = str(uuid.uuid4())
        forked_title = title or f"Fork of {parent.title or session_id}"
        
        forked = ExtendedSessionData(
            session_id=new_id,
            messages=messages_to_copy,
            parent_id=session_id,
            forked_from_message_id=fork_msg_id,
            title=forked_title,
            agent_name=parent.agent_name,
            metadata=copy.deepcopy(parent.metadata),
        )
        
        # Update parent's children list
        parent.children_ids.append(new_id)
        
        self._save_extended_session(forked)
        self._save_extended_session(parent)
        
        return new_id
    
    def get_children(self, session_id: str) -> List[str]:
        """Get all child session IDs."""
        session = self._load_extended_session(session_id)
        return session.children_ids.copy()
    
    def get_parent(self, session_id: str) -> Optional[str]:
        """Get parent session ID."""
        session = self._load_extended_session(session_id)
        return session.parent_id
    
    def get_session_tree(self, session_id: str) -> Dict[str, Any]:
        """
        Get the full session tree starting from a session.
        
        Returns a nested dictionary representing the tree structure.
        """
        session = self._load_extended_session(session_id)
        
        tree = {
            "session_id": session.session_id,
            "title": session.title,
            "message_count": len(session.messages),
            "children": []
        }
        
        for child_id in session.children_ids:
            tree["children"].append(self.get_session_tree(child_id))
        
        return tree
    
    def create_snapshot(
        self,
        session_id: str,
        label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a snapshot of the current session state.
        
        Args:
            session_id: The session to snapshot
            label: Optional label for the snapshot
            metadata: Optional metadata
            
        Returns:
            The snapshot ID
        """
        # Force reload to get latest messages
        session = self._load_extended_session(session_id, force_reload=True)
        
        snapshot = SessionSnapshot(
            session_id=session_id,
            message_index=len(session.messages) - 1 if session.messages else -1,
            label=label,
            metadata=metadata or {},
        )
        
        session.snapshots.append(snapshot)
        self._save_extended_session(session)
        
        return snapshot.id
    
    def get_snapshots(self, session_id: str) -> List[SessionSnapshot]:
        """Get all snapshots for a session."""
        session = self._load_extended_session(session_id)
        return session.snapshots.copy()
    
    def revert_to_snapshot(self, session_id: str, snapshot_id: str) -> bool:
        """
        Revert a session to a snapshot.
        
        Args:
            session_id: The session to revert
            snapshot_id: The snapshot to revert to
            
        Returns:
            True if successful
        """
        session = self._load_extended_session(session_id)
        
        # Find the snapshot
        snapshot = None
        for s in session.snapshots:
            if s.id == snapshot_id:
                snapshot = s
                break
        
        if snapshot is None:
            logger.warning(f"Snapshot {snapshot_id} not found")
            return False
        
        # Revert messages
        if snapshot.message_index >= 0:
            session.messages = session.messages[:snapshot.message_index + 1]
        else:
            session.messages = []
        
        return self._save_extended_session(session)
    
    def revert_to_message(self, session_id: str, message_index: int) -> bool:
        """
        Revert a session to a specific message index.
        
        Args:
            session_id: The session to revert
            message_index: The message index to revert to
            
        Returns:
            True if successful
        """
        # Force reload to get latest messages
        session = self._load_extended_session(session_id, force_reload=True)
        
        if message_index < 0 or message_index >= len(session.messages):
            logger.warning(f"Invalid message index {message_index}")
            return False
        
        session.messages = session.messages[:message_index + 1]
        return self._save_extended_session(session)
    
    def share_session(self, session_id: str) -> bool:
        """Mark a session as shared."""
        session = self._load_extended_session(session_id)
        session.is_shared = True
        return self._save_extended_session(session)
    
    def unshare_session(self, session_id: str) -> bool:
        """Mark a session as not shared."""
        session = self._load_extended_session(session_id)
        session.is_shared = False
        return self._save_extended_session(session)
    
    def is_shared(self, session_id: str) -> bool:
        """Check if a session is shared."""
        session = self._load_extended_session(session_id)
        return session.is_shared
    
    def set_title(self, session_id: str, title: str) -> bool:
        """Set session title."""
        session = self._load_extended_session(session_id)
        session.title = title
        return self._save_extended_session(session)
    
    def get_extended_session(self, session_id: str) -> ExtendedSessionData:
        """Get extended session data."""
        return self._load_extended_session(session_id)
    
    def export_session(self, session_id: str) -> Dict[str, Any]:
        """
        Export a session to a portable format.
        
        Returns a dictionary that can be serialized to JSON.
        """
        # Force reload to get latest data
        session = self._load_extended_session(session_id, force_reload=True)
        return session.to_dict()
    
    def import_session(
        self,
        data: Dict[str, Any],
        new_session_id: Optional[str] = None,
    ) -> str:
        """
        Import a session from exported data.
        
        Args:
            data: The exported session data
            new_session_id: Optional new session ID (generates one if not provided)
            
        Returns:
            The imported session ID
        """
        session = ExtendedSessionData.from_dict(data)
        
        if new_session_id:
            session.session_id = new_session_id
        else:
            session.session_id = str(uuid.uuid4())
        
        # Clear hierarchy references since this is an import
        session.parent_id = None
        session.children_ids = []
        session.forked_from_message_id = None
        
        self._save_extended_session(session)
        return session.session_id


# Global hierarchical store instance
_hierarchical_store: Optional[HierarchicalSessionStore] = None
_hierarchical_lock = threading.Lock()


def get_hierarchical_session_store() -> HierarchicalSessionStore:
    """Get the global hierarchical session store instance."""
    global _hierarchical_store
    
    if _hierarchical_store is None:
        with _hierarchical_lock:
            if _hierarchical_store is None:
                _hierarchical_store = HierarchicalSessionStore()
    
    return _hierarchical_store
