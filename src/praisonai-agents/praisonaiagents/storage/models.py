"""
Storage Models for PraisonAI Agents.

Provides common dataclasses for session/trace info to eliminate duplication
across TrainingSessionInfo, TraceInfo, and similar classes.

DRY: This module extracts the common session metadata pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class BaseSessionInfo:
    """
    Base class for session/trace info.
    
    Provides common fields for session metadata used by:
    - TrainingSessionInfo (train/agents/storage.py)
    - TraceInfo (replay/storage.py)
    - SessionData (session/store.py)
    
    Attributes:
        session_id: Unique session identifier
        path: Path to the session file
        size_bytes: File size in bytes
        created_at: When the session was created
        modified_at: When the session was last modified
        item_count: Number of items (iterations, events, messages, etc.)
    """
    session_id: str
    path: Path
    size_bytes: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    modified_at: datetime = field(default_factory=datetime.now)
    item_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "item_count": self.item_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseSessionInfo":
        """Create from dictionary."""
        created_at = data.get("created_at")
        modified_at = data.get("modified_at")
        
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
            
        if isinstance(modified_at, str):
            modified_at = datetime.fromisoformat(modified_at)
        elif modified_at is None:
            modified_at = datetime.now()
        
        return cls(
            session_id=data["session_id"],
            path=Path(data["path"]),
            size_bytes=data.get("size_bytes", 0),
            created_at=created_at,
            modified_at=modified_at,
            item_count=data.get("item_count", 0),
        )
    
    @classmethod
    def from_path(cls, path: Path, session_id: Optional[str] = None) -> "BaseSessionInfo":
        """
        Create from a file path.
        
        Args:
            path: Path to the session file
            session_id: Optional session ID (defaults to file stem)
            
        Returns:
            BaseSessionInfo with file metadata
        """
        stat = path.stat()
        return cls(
            session_id=session_id or path.stem,
            path=path,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
        )


__all__ = [
    'BaseSessionInfo',
]
