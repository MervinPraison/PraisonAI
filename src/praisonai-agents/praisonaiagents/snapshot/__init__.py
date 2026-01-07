"""
Snapshot Module for PraisonAI Agents.

Provides file change tracking using a shadow git repository,
enabling undo/restore capabilities without affecting the user's
actual git repository.

Features:
- Shadow git repository for tracking changes
- File diff generation
- Snapshot creation and restoration
- Session-based change tracking
- Zero interference with user's git repos

Usage:
    from praisonaiagents.snapshot import FileSnapshot
    
    # Initialize for a project
    snapshot = FileSnapshot("/path/to/project")
    
    # Track current state
    hash = snapshot.track()
    
    # Get diff from a snapshot
    diff = snapshot.diff(hash)
    
    # Restore to a snapshot
    snapshot.restore(hash)
"""

__all__ = [
    "FileSnapshot",
    "SnapshotInfo",
    "FileDiff",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name == "FileSnapshot":
        from .snapshot import FileSnapshot
        return FileSnapshot
    
    if name == "SnapshotInfo":
        from .snapshot import SnapshotInfo
        return SnapshotInfo
    
    if name == "FileDiff":
        from .snapshot import FileDiff
        return FileDiff
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
