"""
Context Trace Writer for PraisonAI.

Writes context events to JSONL files for later replay.
Thread-safe with buffered writes for performance.
"""

import json
import threading
from pathlib import Path
from typing import List, Optional

from .storage import get_trace_path


class ContextTraceWriter:
    """
    JSONL writer for context trace events.
    
    Implements the ContextTraceSink protocol from praisonaiagents.
    Writes events to a JSONL file with buffering for performance.
    
    Usage:
        writer = ContextTraceWriter(session_id="my-session")
        
        # Emit events
        writer.emit(event)
        
        # Flush and close when done
        writer.close()
    """
    
    def __init__(
        self,
        session_id: str,
        traces_dir: Optional[Path] = None,
        buffer_size: int = 100,
        auto_flush: bool = True,
    ):
        """
        Initialize the writer.
        
        Args:
            session_id: Session identifier (used as filename)
            traces_dir: Directory for trace files (default: ~/.praison/traces)
            buffer_size: Number of events to buffer before flushing
            auto_flush: Whether to auto-flush on buffer full
        """
        self._session_id = session_id
        self._path = get_trace_path(session_id, traces_dir)
        self._buffer_size = buffer_size
        self._auto_flush = auto_flush
        
        self._buffer: List[str] = []
        self._lock = threading.Lock()
        self._closed = False
        
        # Clear existing file to prevent appending old traces
        if self._path.exists():
            self._path.unlink()
        
        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)
    
    def emit(self, event) -> None:
        """
        Emit a context event.
        
        Args:
            event: ContextEvent to write (must have to_dict() method)
        """
        if self._closed:
            return
        
        # Serialize event
        try:
            event_dict = event.to_dict()
            json_line = json.dumps(event_dict, default=str)
        except Exception:
            return
        
        with self._lock:
            self._buffer.append(json_line)
            
            if self._auto_flush and len(self._buffer) >= self._buffer_size:
                self._flush_buffer()
    
    def flush(self) -> None:
        """Flush buffered events to disk."""
        with self._lock:
            self._flush_buffer()
    
    def _flush_buffer(self) -> None:
        """Internal flush (must hold lock)."""
        if not self._buffer:
            return
        
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                for line in self._buffer:
                    f.write(line + "\n")
            self._buffer.clear()
        except Exception:
            pass
    
    def close(self) -> None:
        """Close the writer and flush remaining events."""
        if self._closed:
            return
        
        self.flush()
        self._closed = True
    
    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id
    
    @property
    def path(self) -> Path:
        """Get the trace file path."""
        return self._path
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
