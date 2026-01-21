"""
Storage utilities for context traces.

Provides functions for managing trace storage locations and listing traces.
"""

import os
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


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


@dataclass
class TraceInfo:
    """Information about a trace file."""
    session_id: str
    path: Path
    size_bytes: int
    created_at: datetime
    modified_at: datetime
    event_count: int = 0
    
    def to_dict(self):
        return {
            "session_id": self.session_id,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "event_count": self.event_count,
        }


def list_traces(
    traces_dir: Optional[Path] = None,
    limit: int = 50,
) -> List[TraceInfo]:
    """
    List available trace files.
    
    Args:
        traces_dir: Directory to search (default: ~/.praison/traces)
        limit: Maximum number of traces to return
        
    Returns:
        List of TraceInfo objects, sorted by modification time (newest first)
    """
    if traces_dir is None:
        traces_dir = get_traces_dir()
    
    if not traces_dir.exists():
        return []
    
    traces = []
    for trace_file in traces_dir.iterdir():
        if trace_file.is_file() and trace_file.suffix == ".jsonl":
            stat = trace_file.stat()
            
            # Count events (lines) in file
            event_count = 0
            try:
                with open(trace_file, "r") as f:
                    event_count = sum(1 for _ in f)
            except Exception:
                pass
            
            traces.append(TraceInfo(
                session_id=trace_file.stem,
                path=trace_file,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime),
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                event_count=event_count,
            ))
    
    # Sort by modification time (newest first)
    traces.sort(key=lambda t: t.modified_at, reverse=True)
    
    return traces[:limit]


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
    
    Args:
        traces_dir: Directory to clean (default: ~/.praison/traces)
        max_age_days: Delete traces older than this
        max_size_mb: Delete oldest traces if total size exceeds this
        
    Returns:
        Number of files deleted
    """
    if traces_dir is None:
        traces_dir = get_traces_dir()
    
    if not traces_dir.exists():
        return 0
    
    deleted = 0
    now = datetime.now()
    
    # Get all traces sorted by age (oldest first)
    traces = list_traces(traces_dir, limit=10000)
    traces.sort(key=lambda t: t.modified_at)
    
    # Delete old traces
    for trace in traces:
        age_days = (now - trace.modified_at).days
        if age_days > max_age_days:
            try:
                trace.path.unlink()
                deleted += 1
            except Exception:
                pass
    
    # Check total size and delete oldest if needed
    total_size_mb = sum(t.size_bytes for t in traces if t.path.exists()) / (1024 * 1024)
    
    if total_size_mb > max_size_mb:
        # Re-fetch remaining traces
        remaining = list_traces(traces_dir, limit=10000)
        remaining.sort(key=lambda t: t.modified_at)
        
        for trace in remaining:
            if total_size_mb <= max_size_mb:
                break
            try:
                trace.path.unlink()
                total_size_mb -= trace.size_bytes / (1024 * 1024)
                deleted += 1
            except Exception:
                pass
    
    return deleted
