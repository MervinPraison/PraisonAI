"""
Event types and dataclasses for InteractiveCore.

These events are emitted by InteractiveCore and consumed by frontends
(Rich REPL, Textual TUI, etc.) for rendering.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class InteractiveEventType(Enum):
    """Types of events emitted by InteractiveCore."""
    
    # Message lifecycle
    MESSAGE_START = "message.start"
    MESSAGE_CHUNK = "message.chunk"
    MESSAGE_END = "message.end"
    
    # Tool execution
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    
    # Stage transitions (PLAN → EXPLORE → BUILD → REVIEW)
    STAGE_CHANGE = "stage.change"
    
    # Approval/permission flow
    APPROVAL_ASKED = "approval.asked"
    APPROVAL_ANSWERED = "approval.answered"
    
    # Session lifecycle
    SESSION_CREATED = "session.created"
    SESSION_RESUMED = "session.resumed"
    
    # Status
    ERROR = "error"
    IDLE = "idle"


class ApprovalDecision(Enum):
    """Possible decisions for approval requests."""
    
    ONCE = "once"  # Allow this one time
    ALWAYS = "always"  # Always allow this pattern (persistent)
    ALWAYS_SESSION = "always_session"  # Always allow for this session only
    REJECT = "reject"  # Reject this action


@dataclass
class InteractiveEvent:
    """Event emitted by InteractiveCore."""
    
    type: InteractiveEventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }


@dataclass
class ApprovalRequest:
    """Request for user approval before executing an action."""
    
    action_type: str  # e.g., "file_write", "shell_command", "file_read"
    description: str  # Human-readable description
    tool_name: str  # Name of the tool requesting approval
    parameters: Dict[str, Any]  # Tool parameters
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "action_type": self.action_type,
            "description": self.description,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
        }
    
    def matches_pattern(self, pattern: str) -> bool:
        """Check if this request matches an approval pattern.
        
        Pattern format: "action_type:path_pattern"
        Examples:
            - "file_read:*" matches all file reads
            - "file_write:/tmp/*" matches writes to /tmp/
            - "shell_command:ls*" matches ls commands
        """
        if ":" not in pattern:
            return self.action_type == pattern
        
        action_pattern, path_pattern = pattern.split(":", 1)
        
        if action_pattern != "*" and action_pattern != self.action_type:
            return False
        
        if path_pattern == "*":
            return True
        
        # Simple glob matching
        import fnmatch
        path = self.parameters.get("path", self.parameters.get("command", ""))
        return fnmatch.fnmatch(str(path), path_pattern)


@dataclass
class ApprovalResponse:
    """Response to an approval request."""
    
    request_id: str
    decision: ApprovalDecision
    remember_pattern: Optional[str] = None  # Pattern to remember for ALWAYS decisions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "remember_pattern": self.remember_pattern,
        }
