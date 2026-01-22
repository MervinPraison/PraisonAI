"""
Session management for PraisonAI CLI.

Provides persistence and resume functionality for sessions.
"""

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..configuration.paths import get_sessions_dir, ensure_config_dirs
from .identifiers import RunContext

if TYPE_CHECKING:
    from praisonaiagents.storage.protocols import StorageBackendProtocol


@dataclass
class SessionMetadata:
    """Metadata for a session."""
    session_id: str
    run_id: str
    trace_id: str
    created_at: datetime
    updated_at: datetime
    name: Optional[str] = None
    workspace: Optional[str] = None
    config_summary: Dict[str, Any] = field(default_factory=dict)
    event_count: int = 0
    status: str = "active"  # active, completed, error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "name": self.name,
            "workspace": self.workspace,
            "config_summary": self.config_summary,
            "event_count": self.event_count,
            "status": self.status,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMetadata":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            run_id=data["run_id"],
            trace_id=data["trace_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            name=data.get("name"),
            workspace=data.get("workspace"),
            config_summary=data.get("config_summary", {}),
            event_count=data.get("event_count", 0),
            status=data.get("status", "active"),
        )


class SessionManager:
    """
    Manages session persistence and retrieval.
    
    Sessions are stored in ~/.praison/sessions/<session_id>/
    Each session contains:
    - metadata.json: Session metadata
    - events.jsonl: Stream of events (NDJSON)
    
    Supports pluggable backends (file, sqlite, redis) via the backend parameter.
    
    Example with SQLite backend:
        ```python
        from praisonaiagents.storage import SQLiteBackend
        backend = SQLiteBackend("~/.praison/sessions.db")
        manager = SessionManager(backend=backend)
        ```
    """
    
    def __init__(
        self,
        sessions_dir: Optional[Path] = None,
        backend: Optional["StorageBackendProtocol"] = None,
    ):
        """
        Initialize session manager.
        
        Args:
            sessions_dir: Directory for file-based storage
            backend: Optional storage backend (file, sqlite, redis).
                     If provided, sessions_dir is ignored.
        """
        self.sessions_dir = sessions_dir or get_sessions_dir()
        self._backend = backend
        
        if backend is None:
            ensure_config_dirs()
    
    def _get_session_dir(self, session_id: str) -> Path:
        """Get the directory for a session."""
        return self.sessions_dir / session_id
    
    def _get_metadata_path(self, session_id: str) -> Path:
        """Get the metadata file path for a session."""
        return self._get_session_dir(session_id) / "metadata.json"
    
    def _get_events_path(self, session_id: str) -> Path:
        """Get the events file path for a session."""
        return self._get_session_dir(session_id) / "events.jsonl"
    
    def create(self, context: RunContext, name: Optional[str] = None) -> SessionMetadata:
        """
        Create a new session from a run context.
        
        Args:
            context: Run context to create session from
            name: Optional session name
            
        Returns:
            Session metadata
        """
        session_id = context.run_id  # Use run_id as session_id
        session_dir = self._get_session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)
        
        now = datetime.utcnow()
        metadata = SessionMetadata(
            session_id=session_id,
            run_id=context.run_id,
            trace_id=context.trace_id,
            created_at=now,
            updated_at=now,
            name=name,
            workspace=context.workspace,
            config_summary=context.config_summary,
        )
        
        # Save metadata
        self._save_metadata(metadata)
        
        # Create empty events file
        self._get_events_path(session_id).touch()
        
        return metadata
    
    def _save_metadata(self, metadata: SessionMetadata) -> None:
        """Save session metadata."""
        if self._backend is not None:
            self._backend.save(f"session:{metadata.session_id}:meta", metadata.to_dict())
            return
        
        path = self._get_metadata_path(metadata.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata.to_dict(), f, indent=2)
    
    def _load_metadata(self, session_id: str) -> Optional[SessionMetadata]:
        """Load session metadata."""
        if self._backend is not None:
            data = self._backend.load(f"session:{session_id}:meta")
            if data:
                try:
                    return SessionMetadata.from_dict(data)
                except (KeyError, TypeError):
                    return None
            return None
        
        path = self._get_metadata_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionMetadata.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None
    
    def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """
        Append an event to a session.
        
        Args:
            session_id: Session ID
            event: Event data to append
        """
        if self._backend is not None:
            # Load existing events, append, save
            events = self._backend.load(f"session:{session_id}:events") or []
            events.append(event)
            self._backend.save(f"session:{session_id}:events", events)
        else:
            events_path = self._get_events_path(session_id)
            if not events_path.parent.exists():
                return
            
            with open(events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        
        # Update metadata
        metadata = self._load_metadata(session_id)
        if metadata:
            metadata.event_count += 1
            metadata.updated_at = datetime.utcnow()
            self._save_metadata(metadata)
    
    def get(self, session_id: str) -> Optional[SessionMetadata]:
        """Get session metadata by ID."""
        return self._load_metadata(session_id)
    
    def list(self, limit: int = 50) -> List[SessionMetadata]:
        """
        List all sessions, sorted by updated_at descending.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of session metadata
        """
        sessions = []
        
        if self._backend is not None:
            # List all session metadata keys
            keys = self._backend.list_keys(prefix="session:")
            session_ids = set()
            for key in keys:
                # Extract session_id from "session:<id>:meta" or "session:<id>:events"
                parts = key.split(":")
                if len(parts) >= 2:
                    session_ids.add(parts[1])
            
            for session_id in session_ids:
                metadata = self._load_metadata(session_id)
                if metadata:
                    sessions.append(metadata)
        else:
            if not self.sessions_dir.exists():
                return sessions
            
            for session_dir in self.sessions_dir.iterdir():
                if session_dir.is_dir():
                    metadata = self._load_metadata(session_dir.name)
                    if metadata:
                        sessions.append(metadata)
        
        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        
        return sessions[:limit]
    
    def delete(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        if self._backend is not None:
            deleted_meta = self._backend.delete(f"session:{session_id}:meta")
            deleted_events = self._backend.delete(f"session:{session_id}:events")
            return deleted_meta or deleted_events
        
        session_dir = self._get_session_dir(session_id)
        if not session_dir.exists():
            return False
        
        shutil.rmtree(session_dir)
        return True
    
    def get_events(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all events for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of events
        """
        if self._backend is not None:
            return self._backend.load(f"session:{session_id}:events") or []
        
        events_path = self._get_events_path(session_id)
        if not events_path.exists():
            return []
        
        events = []
        with open(events_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        
        return events
    
    def export(self, session_id: str, format: str = "md") -> Optional[str]:
        """
        Export a session to a string.
        
        Args:
            session_id: Session ID
            format: Export format ("md" or "json")
            
        Returns:
            Exported content or None if not found
        """
        metadata = self._load_metadata(session_id)
        if not metadata:
            return None
        
        events = self.get_events(session_id)
        
        if format == "json":
            return json.dumps({
                "metadata": metadata.to_dict(),
                "events": events,
            }, indent=2, default=str)
        
        # Markdown format
        lines = [
            f"# Session: {metadata.name or metadata.session_id}",
            "",
            f"- **Run ID**: {metadata.run_id}",
            f"- **Trace ID**: {metadata.trace_id}",
            f"- **Created**: {metadata.created_at.isoformat()}",
            f"- **Status**: {metadata.status}",
            "",
            "## Events",
            "",
        ]
        
        for event in events:
            event_type = event.get("event", "unknown")
            timestamp = event.get("timestamp", "")
            message = event.get("message", "")
            
            lines.append(f"### {event_type} ({timestamp})")
            if message:
                lines.append(f"\n{message}")
            
            data = event.get("data", {})
            if data:
                lines.append("\n```json")
                lines.append(json.dumps(data, indent=2, default=str))
                lines.append("```")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def update_status(self, session_id: str, status: str) -> None:
        """Update session status."""
        metadata = self._load_metadata(session_id)
        if metadata:
            metadata.status = status
            metadata.updated_at = datetime.utcnow()
            self._save_metadata(metadata)


# Global session manager
_session_manager: Optional[SessionManager] = None
_session_backend: Optional["StorageBackendProtocol"] = None


def set_session_backend(backend: "StorageBackendProtocol") -> None:
    """Set the storage backend for session manager."""
    global _session_backend, _session_manager
    _session_backend = backend
    # Reset manager to use new backend
    _session_manager = None


def get_session_manager() -> SessionManager:
    """Get the global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(backend=_session_backend)
    return _session_manager
