"""
ACP session management.

Handles session creation, persistence, and resume functionality.
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ACPSession:
    """Represents an ACP conversation session."""
    
    session_id: str
    workspace: Path
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    
    # Agent attribution
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    # Session state
    mode: str = "manual"  # manual, auto, full_auto
    model: Optional[str] = None
    
    # Conversation history (for resume)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    
    # MCP servers
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)
    
    @classmethod
    def create(cls, workspace: Path, agent_id: Optional[str] = None) -> "ACPSession":
        """Create a new session."""
        session_id = f"sess_{uuid.uuid4().hex[:16]}"
        return cls(
            session_id=session_id,
            workspace=workspace,
            agent_id=agent_id,
            run_id=f"run_{uuid.uuid4().hex[:8]}",
            trace_id=f"trace_{uuid.uuid4().hex[:8]}",
        )
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()
    
    def add_message(self, role: str, content: Any) -> None:
        """Add a message to the conversation history."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })
        self.update_activity()
    
    def add_tool_call(self, tool_call_id: str, title: str, status: str, **kwargs) -> None:
        """Add a tool call to the history."""
        self.tool_calls.append({
            "tool_call_id": tool_call_id,
            "title": title,
            "status": status,
            "timestamp": time.time(),
            **kwargs,
        })
        self.update_activity()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "session_id": self.session_id,
            "workspace": str(self.workspace),
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "mode": self.mode,
            "model": self.model,
            "messages": self.messages,
            "tool_calls": self.tool_calls,
            "mcp_servers": self.mcp_servers,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPSession":
        """Deserialize session from dictionary."""
        return cls(
            session_id=data["session_id"],
            workspace=Path(data["workspace"]),
            created_at=data.get("created_at", time.time()),
            last_activity=data.get("last_activity", time.time()),
            agent_id=data.get("agent_id"),
            run_id=data.get("run_id"),
            trace_id=data.get("trace_id"),
            mode=data.get("mode", "manual"),
            model=data.get("model"),
            messages=data.get("messages", []),
            tool_calls=data.get("tool_calls", []),
            mcp_servers=data.get("mcp_servers", []),
        )


class SessionStore:
    """Persistent storage for ACP sessions."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize session store."""
        if storage_dir is None:
            storage_dir = Path.home() / ".praison" / "acp" / "sessions"
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._last_session_file = self.storage_dir / ".last_session"
    
    def _session_path(self, session_id: str) -> Path:
        """Get path for session file."""
        return self.storage_dir / f"{session_id}.json"
    
    def save(self, session: ACPSession) -> None:
        """Save session to disk."""
        try:
            path = self._session_path(session.session_id)
            with open(path, "w") as f:
                json.dump(session.to_dict(), f, indent=2)
            
            # Update last session pointer
            with open(self._last_session_file, "w") as f:
                f.write(session.session_id)
            
            logger.debug(f"Saved session {session.session_id}")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
    
    def load(self, session_id: str) -> Optional[ACPSession]:
        """Load session from disk."""
        try:
            path = self._session_path(session_id)
            if not path.exists():
                logger.warning(f"Session not found: {session_id}")
                return None
            
            with open(path) as f:
                data = json.load(f)
            
            return ACPSession.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return None
    
    def load_last(self) -> Optional[ACPSession]:
        """Load the most recent session."""
        try:
            if not self._last_session_file.exists():
                return None
            
            with open(self._last_session_file) as f:
                session_id = f.read().strip()
            
            if session_id:
                return self.load(session_id)
            return None
        except Exception as e:
            logger.error(f"Failed to load last session: {e}")
            return None
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        try:
            path = self._session_path(session_id)
            if path.exists():
                path.unlink()
                logger.debug(f"Deleted session {session_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete session: {e}")
            return False
    
    def list_sessions(self, limit: int = 50) -> List[ACPSession]:
        """List all sessions, sorted by last activity."""
        sessions = []
        try:
            for path in self.storage_dir.glob("sess_*.json"):
                try:
                    with open(path) as f:
                        data = json.load(f)
                    sessions.append(ACPSession.from_dict(data))
                except Exception:
                    continue
            
            # Sort by last activity, most recent first
            sessions.sort(key=lambda s: s.last_activity, reverse=True)
            return sessions[:limit]
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []
    
    def cleanup_old_sessions(self, max_age_days: int = 30) -> int:
        """Remove sessions older than max_age_days."""
        cutoff = time.time() - (max_age_days * 24 * 60 * 60)
        removed = 0
        
        for session in self.list_sessions(limit=1000):
            if session.last_activity < cutoff:
                if self.delete(session.session_id):
                    removed += 1
        
        return removed
