"""
Checkpoint Types for PraisonAI Agents.

Defines the core types, enums, and dataclasses for the checkpoint system.
"""

import os
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path


class CheckpointEvent(str, Enum):
    """Events emitted by the checkpoint service."""
    INITIALIZED = "initialized"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    ERROR = "error"


@dataclass
class CheckpointConfig:
    """Configuration for the checkpoint service."""
    workspace_dir: str
    storage_dir: Optional[str] = None
    enabled: bool = True
    auto_checkpoint: bool = True  # Auto-checkpoint before file modifications
    max_checkpoints: int = 100  # Maximum checkpoints to keep
    exclude_patterns: List[str] = field(default_factory=lambda: [
        ".git",
        ".praison",
        "__pycache__",
        "*.pyc",
        ".env",
        "node_modules",
        ".venv",
        "venv",
        "*.log"
    ])
    
    def __post_init__(self):
        # Expand paths
        self.workspace_dir = os.path.expanduser(self.workspace_dir)
        if self.storage_dir:
            self.storage_dir = os.path.expanduser(self.storage_dir)
        else:
            # Default storage in user's home directory
            self.storage_dir = os.path.expanduser("~/.praison/checkpoints")
    
    def get_checkpoint_dir(self) -> str:
        """Get the checkpoint directory for this workspace."""
        # Hash the workspace path to create a unique directory
        import hashlib
        workspace_hash = hashlib.sha256(
            self.workspace_dir.encode()
        ).hexdigest()[:12]
        return os.path.join(self.storage_dir, workspace_hash)


@dataclass
class Checkpoint:
    """Represents a single checkpoint."""
    id: str  # Git commit hash
    short_id: str  # Short hash (8 chars)
    message: str
    timestamp: datetime
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    
    @classmethod
    def from_git_commit(cls, commit_hash: str, message: str, timestamp: str) -> "Checkpoint":
        """Create a Checkpoint from git commit info."""
        return cls(
            id=commit_hash,
            short_id=commit_hash[:8],
            message=message,
            timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "short_id": self.short_id,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions
        }


@dataclass
class FileDiff:
    """Represents a diff for a single file."""
    path: str
    absolute_path: str
    status: str  # added, modified, deleted
    additions: int = 0
    deletions: int = 0
    before_content: Optional[str] = None
    after_content: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "absolute_path": self.absolute_path,
            "status": self.status,
            "additions": self.additions,
            "deletions": self.deletions
        }


@dataclass
class CheckpointDiff:
    """Represents a diff between two checkpoints."""
    from_checkpoint: str
    to_checkpoint: Optional[str]  # None means current working directory
    files: List[FileDiff] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    
    def __post_init__(self):
        # Calculate totals
        self.total_additions = sum(f.additions for f in self.files)
        self.total_deletions = sum(f.deletions for f in self.files)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "from_checkpoint": self.from_checkpoint,
            "to_checkpoint": self.to_checkpoint,
            "files": [f.to_dict() for f in self.files],
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions
        }


@dataclass
class CheckpointResult:
    """Result of a checkpoint operation."""
    success: bool
    checkpoint: Optional[Checkpoint] = None
    error: Optional[str] = None
    
    @classmethod
    def ok(cls, checkpoint: Checkpoint) -> "CheckpointResult":
        """Create a successful result."""
        return cls(success=True, checkpoint=checkpoint)
    
    @classmethod
    def fail(cls, error: str) -> "CheckpointResult":
        """Create a failed result."""
        return cls(success=False, error=error)
