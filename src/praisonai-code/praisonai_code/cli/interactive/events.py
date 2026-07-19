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


def derive_permission_pattern(request: "ApprovalRequest", scope: str = "command") -> str:
    """Derive the persisted permission pattern for an approval request.

    Mirrors the console backend's ``_create_pattern`` so interactive frontends
    and the non-interactive console backend scope grants identically.

    Args:
        request: The approval request being persisted.
        scope: ``"command"`` (default) derives the *narrowest reasonable*
            pattern so approving a single command does not silently grant
            unrestricted use of a tool. ``"tool"`` is the explicit, clearly
            labelled "allow all uses of this tool" choice that emits the
            blanket ``action_type:*`` pattern.

    Returns:
        A permission glob pattern. For ``scope="command"`` the result is
        **never** the blanket ``action_type:*``: shell commands are generalised
        to a reusable command-prefix (e.g. ``shell_command:git status *``) via
        the shared core helper, and other tools scope to the concrete
        path/argument, falling back to a literal (single-use) target so the
        rule can only match the exact invocation the user approved.
    """
    action_type = request.action_type

    # Explicit, clearly-labelled "always allow all uses of this tool" only.
    if scope == "tool":
        return f"{action_type}:*"

    params = request.parameters or {}

    # Shell tools: generalise to a reusable command-prefix via the shared core
    # helper so interactive and declarative rules scope identically. Unknown or
    # compound commands stay literal (fail-closed).
    command = params.get("command")
    if isinstance(command, str) and command.strip():
        try:
            from praisonaiagents.permissions import derive_pattern

            # derive_pattern only generalises bash:/shell: targets, so map the
            # action type onto a shell prefix for derivation, then restore it.
            derived = derive_pattern(f"shell:{command}")
            suffix = derived[len("shell:"):]
            return f"{action_type}:{suffix}"
        except ImportError:
            pass
        except Exception:  # pragma: no cover - fail-closed on unexpected errors
            import logging as _logging
            _logging.getLogger(__name__).debug(
                "derive_pattern failed for %r; falling back to literal command",
                command,
                exc_info=True,
            )
        return f"{action_type}:{command}"

    # Non-shell tools: scope to the concrete path/target when available so the
    # persisted rule matches only that resource, never the whole tool.
    path = params.get("path")
    if isinstance(path, str) and path:
        return f"{action_type}:{path}"

    # No usable target: match only the bare invocation, never the wildcard.
    return f"{action_type}:"


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
