"""WebSocket message protocol for browser ↔ server communication.

These are the wire-format messages exchanged over WebSocket.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Literal
import json


@dataclass
class WSMessage:
    """Base WebSocket message."""
    type: str
    session_id: str = ""
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_json(cls, data: str) -> "WSMessage":
        """Deserialize from JSON string."""
        parsed = json.loads(data)
        return cls(**parsed)


@dataclass  
class ObservationMessage(WSMessage):
    """Observation from browser extension."""
    type: str = "observation"
    task: str = ""
    url: str = ""
    title: str = ""
    screenshot: str = ""
    elements: List[Dict[str, Any]] = field(default_factory=list)
    console_logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    step_number: int = 0


@dataclass
class ActionMessage(WSMessage):
    """Action command to browser extension."""
    type: str = "action"
    action: str = "done"
    selector: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    direction: Optional[str] = None
    expression: Optional[str] = None
    thought: str = ""
    done: bool = False
    error: Optional[str] = None


@dataclass
class StartSessionMessage(WSMessage):
    """Start a new automation session."""
    type: str = "start_session"
    goal: str = ""
    model: str = "gpt-4o-mini"


@dataclass
class StopSessionMessage(WSMessage):
    """Stop current session."""
    type: str = "stop_session"


@dataclass
class StatusMessage(WSMessage):
    """Status update."""
    type: str = "status"
    status: Literal["connected", "running", "completed", "failed", "stopped"] = "connected"
    message: str = ""


@dataclass
class ErrorMessage(WSMessage):
    """Error message."""
    type: str = "error"
    error: str = ""
    code: str = ""


def parse_message(data: str) -> WSMessage:
    """Parse incoming WebSocket message."""
    try:
        parsed = json.loads(data)
        msg_type = parsed.get("type", "")
        
        if msg_type == "observation":
            return ObservationMessage(**parsed)
        elif msg_type == "action":
            return ActionMessage(**parsed)
        elif msg_type == "start_session":
            return StartSessionMessage(**parsed)
        elif msg_type == "stop_session":
            return StopSessionMessage(**parsed)
        elif msg_type == "status":
            return StatusMessage(**parsed)
        elif msg_type == "error":
            return ErrorMessage(**parsed)
        else:
            return WSMessage(**parsed)
    except Exception as e:
        return ErrorMessage(type="error", error=str(e), code="PARSE_ERROR")
