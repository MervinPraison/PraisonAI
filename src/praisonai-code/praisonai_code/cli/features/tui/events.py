"""
Custom events for PraisonAI TUI.

Defines event types for communication between TUI components.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
import time


class TUIEventType(str, Enum):
    """Types of TUI events."""
    # User input events
    MESSAGE_SUBMITTED = "message_submitted"
    COMMAND_EXECUTED = "command_executed"
    
    # Queue events
    RUN_QUEUED = "run_queued"
    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    
    # Output events
    OUTPUT_CHUNK = "output_chunk"
    OUTPUT_COMPLETE = "output_complete"
    
    # Tool events
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_APPROVAL_REQUIRED = "tool_approval_required"
    
    # Session events
    SESSION_STARTED = "session_started"
    SESSION_SAVED = "session_saved"
    SESSION_LOADED = "session_loaded"
    
    # UI events
    SCREEN_CHANGED = "screen_changed"
    FOCUS_CHANGED = "focus_changed"
    ERROR_OCCURRED = "error_occurred"
    STATUS_UPDATED = "status_updated"


@dataclass
class TUIEvent:
    """A TUI event."""
    event_type: TUIEventType
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Optional identifiers
    run_id: Optional[str] = None
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    
    @classmethod
    def message_submitted(cls, content: str, **kwargs) -> "TUIEvent":
        """Create a message submitted event."""
        return cls(
            event_type=TUIEventType.MESSAGE_SUBMITTED,
            data={"content": content, **kwargs}
        )
    
    @classmethod
    def output_chunk(cls, run_id: str, content: str, **kwargs) -> "TUIEvent":
        """Create an output chunk event."""
        return cls(
            event_type=TUIEventType.OUTPUT_CHUNK,
            run_id=run_id,
            data={"content": content, **kwargs}
        )
    
    @classmethod
    def run_completed(cls, run_id: str, output: str, **kwargs) -> "TUIEvent":
        """Create a run completed event."""
        return cls(
            event_type=TUIEventType.RUN_COMPLETED,
            run_id=run_id,
            data={"output": output, **kwargs}
        )
    
    @classmethod
    def error(cls, message: str, **kwargs) -> "TUIEvent":
        """Create an error event."""
        return cls(
            event_type=TUIEventType.ERROR_OCCURRED,
            data={"message": message, **kwargs}
        )
    
    @classmethod
    def status_update(cls, status: str, **kwargs) -> "TUIEvent":
        """Create a status update event."""
        return cls(
            event_type=TUIEventType.STATUS_UPDATED,
            data={"status": status, **kwargs}
        )
