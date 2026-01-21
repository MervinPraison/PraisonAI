"""
Context Trace Reader for PraisonAI.

Reads context events from JSONL files for replay.
"""

import json
from pathlib import Path
from typing import Iterator, List, Optional

from .storage import get_trace_path


class ContextTraceReader:
    """
    JSONL reader for context trace events.
    
    Reads events from a trace file and converts them to ContextEvent objects.
    Supports iteration and random access.
    
    Usage:
        reader = ContextTraceReader("my-session")
        
        # Iterate over events
        for event in reader:
            print(event.event_type)
        
        # Random access
        event = reader[5]
        
        # Get all events
        events = reader.get_all()
    """
    
    def __init__(
        self,
        session_id_or_path: str,
        traces_dir: Optional[Path] = None,
    ):
        """
        Initialize the reader.
        
        Args:
            session_id_or_path: Session ID or full path to trace file
            traces_dir: Directory for trace files (if session_id provided)
        """
        # Determine path
        if "/" in session_id_or_path or session_id_or_path.endswith(".jsonl"):
            self._path = Path(session_id_or_path).expanduser()
            self._session_id = self._path.stem
        else:
            self._session_id = session_id_or_path
            self._path = get_trace_path(session_id_or_path, traces_dir)
        
        self._events: Optional[List] = None
    
    def _load_events(self) -> List:
        """Load all events from file."""
        if self._events is not None:
            return self._events
        
        # Lazy import to avoid circular dependency
        try:
            from praisonaiagents.trace.context_events import ContextEvent
        except ImportError:
            # Fallback: return raw dicts if praisonaiagents not available
            ContextEvent = None
        
        events = []
        
        if not self._path.exists():
            self._events = events
            return events
        
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        if ContextEvent is not None:
                            event = ContextEvent.from_dict(data)
                        else:
                            event = data
                        events.append(event)
                    except (json.JSONDecodeError, Exception):
                        continue
        except Exception:
            pass
        
        self._events = events
        return events
    
    def __iter__(self) -> Iterator:
        """Iterate over events."""
        return iter(self._load_events())
    
    def __len__(self) -> int:
        """Get number of events."""
        return len(self._load_events())
    
    def __getitem__(self, index: int):
        """Get event by index."""
        return self._load_events()[index]
    
    def get_all(self) -> List:
        """Get all events as a list."""
        return self._load_events().copy()
    
    def get_by_agent(self, agent_name: str) -> List:
        """Get events for a specific agent."""
        return [e for e in self._load_events() if getattr(e, 'agent_name', None) == agent_name]
    
    def get_by_type(self, event_type: str) -> List:
        """Get events of a specific type."""
        events = self._load_events()
        result = []
        for e in events:
            # Handle both ContextEvent objects and dicts
            if hasattr(e, 'event_type'):
                et = e.event_type
                if hasattr(et, 'value'):
                    et = et.value
                if et == event_type:
                    result.append(e)
            elif isinstance(e, dict) and e.get('event_type') == event_type:
                result.append(e)
        return result
    
    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id
    
    @property
    def path(self) -> Path:
        """Get the trace file path."""
        return self._path
    
    @property
    def exists(self) -> bool:
        """Check if trace file exists."""
        return self._path.exists()
    
    def reload(self) -> None:
        """Reload events from file."""
        self._events = None
        self._load_events()
