"""
UI Event types for backend communication.

Events flow from InteractiveCore to UI backends for rendering.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class UIEventType(Enum):
    """Event types emitted by InteractiveCore to UI backends."""
    
    # Message lifecycle
    MESSAGE_START = "message.start"
    MESSAGE_CHUNK = "message.chunk"
    MESSAGE_END = "message.end"
    
    # Tool lifecycle
    TOOL_START = "tool.start"
    TOOL_PROGRESS = "tool.progress"
    TOOL_END = "tool.end"
    
    # Approval flow
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_RESPONSE = "approval.response"
    
    # Status updates
    STATUS_UPDATE = "status.update"
    STATUS_CLEAR = "status.clear"
    
    # Errors
    ERROR = "error"
    WARNING = "warning"
    
    # Session events
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    
    # Agent events (multi-agent)
    AGENT_SWITCH = "agent.switch"
    
    # Input events
    INPUT_REQUEST = "input.request"
    INPUT_RECEIVED = "input.received"


@dataclass
class UIEvent:
    """A UI event with type and data payload."""
    
    event_type: UIEventType
    data: Dict[str, Any] = field(default_factory=dict)
    agent_name: Optional[str] = None
    timestamp: Optional[float] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            import time
            self.timestamp = time.time()
