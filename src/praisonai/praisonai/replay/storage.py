"""
Storage utilities for context traces.

Provides functions for managing trace storage locations and listing traces.
"""

import os
from pathlib import Path
from typing import List, Optional

# DRY: Import base classes from praisonaiagents.storage
from praisonaiagents.storage.models import BaseSessionInfo
from praisonaiagents.storage.base import list_json_sessions, cleanup_old_sessions as _cleanup_old_sessions


DEFAULT_TRACES_DIR = "~/.praison/traces"


def get_traces_dir() -> Path:
    """
    Get the traces directory path.
    
    Returns:
        Path to traces directory (creates if not exists)
    """
    traces_dir = Path(os.path.expanduser(DEFAULT_TRACES_DIR))
    traces_dir.mkdir(parents=True, exist_ok=True)
    return traces_dir


class TraceInfo(BaseSessionInfo):
    """
    Information about a trace file.
    
    DRY: Inherits from BaseSessionInfo which provides:
    - session_id, path, size_bytes, created_at, modified_at, item_count
    - to_dict(), from_dict(), from_path() methods
    """
    
    @property
    def event_count(self) -> int:
        """Alias for item_count for backward compatibility."""
        return self.item_count
    
    def to_dict(self):
        """Override to include event_count for backward compatibility."""
        d = super().to_dict()
        d["event_count"] = self.event_count
        return d


def list_traces(
    traces_dir: Optional[Path] = None,
    limit: int = 50,
) -> List[TraceInfo]:
    """
    List available trace files.
    
    DRY: Uses list_json_sessions from praisonaiagents.storage.base.
    
    Args:
        traces_dir: Directory to search (default: ~/.praison/traces)
        limit: Maximum number of traces to return
        
    Returns:
        List of TraceInfo objects, sorted by modification time (newest first)
    """
    if traces_dir is None:
        traces_dir = get_traces_dir()
    
    # DRY: Use common list_json_sessions function with .jsonl suffix
    base_sessions = list_json_sessions(Path(traces_dir), suffix=".jsonl", limit=limit)
    
    # Convert BaseSessionInfo to TraceInfo for backward compatibility
    return [
        TraceInfo(
            session_id=s.session_id,
            path=s.path,
            size_bytes=s.size_bytes,
            created_at=s.created_at,
            modified_at=s.modified_at,
            item_count=s.item_count,
        )
        for s in base_sessions
    ]


def get_trace_path(session_id: str, traces_dir: Optional[Path] = None) -> Path:
    """
    Get the path for a trace file.
    
    Args:
        session_id: Session identifier
        traces_dir: Directory for traces (default: ~/.praison/traces)
        
    Returns:
        Path to the trace file
    """
    if traces_dir is None:
        traces_dir = get_traces_dir()
    
    return traces_dir / f"{session_id}.jsonl"


def cleanup_old_traces(
    traces_dir: Optional[Path] = None,
    max_age_days: int = 7,
    max_size_mb: int = 100,
) -> int:
    """
    Clean up old trace files.
    
    DRY: Uses cleanup_old_sessions from praisonaiagents.storage.base.
    
    Args:
        traces_dir: Directory to clean (default: ~/.praison/traces)
        max_age_days: Delete traces older than this
        max_size_mb: Delete oldest traces if total size exceeds this
        
    Returns:
        Number of files deleted
    """
    if traces_dir is None:
        traces_dir = get_traces_dir()
    
    # DRY: Use common cleanup function with .jsonl suffix
    return _cleanup_old_sessions(
        storage_dir=Path(traces_dir),
        suffix=".jsonl",
        max_age_days=max_age_days,
        max_size_mb=max_size_mb,
    )
