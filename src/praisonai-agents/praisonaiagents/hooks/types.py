"""
Hook Types for PraisonAI Agents.

Defines the core types, enums, and dataclasses for the hook system.
"""

import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Union, Literal


class HookEvent(str, Enum):
    """Event names for the hook system."""
    # Tool lifecycle
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    
    # Agent lifecycle
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    
    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    
    # LLM lifecycle
    BEFORE_LLM = "before_llm"
    AFTER_LLM = "after_llm"
    
    # Error handling
    ON_ERROR = "on_error"
    ON_RETRY = "on_retry"
    
    # Message lifecycle (for bot/channel integrations)
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"
    
    # Gateway lifecycle
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"
    
    # Compaction (memory management)
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"
    
    # Tool result persistence (for modifying tool results before storage)
    TOOL_RESULT_PERSIST = "tool_result_persist"
    
    # Claude Code parity events
    USER_PROMPT_SUBMIT = "user_prompt_submit"  # When user submits a prompt
    NOTIFICATION = "notification"              # When notification is sent
    SUBAGENT_STOP = "subagent_stop"           # When subagent completes
    SETUP = "setup"                           # On initialization/maintenance


# Decision types for hook outputs
HookDecision = Literal["allow", "deny", "block", "ask", None]


@dataclass
class HookInput:
    """Base hook input - common fields for all events."""
    session_id: str
    cwd: str
    event_name: str
    timestamp: str
    agent_name: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "cwd": self.cwd,
            "event_name": self.event_name,
            "timestamp": self.timestamp,
            "agent_name": self.agent_name,
            **self.extra
        }


@dataclass
class HookOutput:
    """Base hook output - common fields for all events."""
    proceed: bool = True
    stop_reason: Optional[str] = None
    suppress_output: bool = False
    system_message: Optional[str] = None
    decision: HookDecision = None
    reason: Optional[str] = None
    modified_data: Optional[Dict[str, Any]] = None
    
    def is_blocking(self) -> bool:
        """Check if this output represents a blocking decision."""
        return self.decision in ("block", "deny")
    
    def should_stop(self) -> bool:
        """Check if execution should stop."""
        return not self.proceed
    
    def get_reason(self) -> str:
        """Get the effective reason for blocking or stopping."""
        return self.reason or self.stop_reason or "No reason provided"


@dataclass
class HookResult:
    """Result from a hook execution."""
    decision: HookDecision = "allow"
    reason: Optional[str] = None
    modified_input: Optional[Dict[str, Any]] = None
    additional_context: Optional[str] = None
    suppress_output: bool = False
    
    @classmethod
    def allow(cls, reason: Optional[str] = None) -> "HookResult":
        """Create an allow result."""
        return cls(decision="allow", reason=reason)
    
    @classmethod
    def deny(cls, reason: str) -> "HookResult":
        """Create a deny result."""
        return cls(decision="deny", reason=reason)
    
    @classmethod
    def block(cls, reason: str) -> "HookResult":
        """Create a block result."""
        return cls(decision="block", reason=reason)
    
    @classmethod
    def ask(cls, reason: str) -> "HookResult":
        """Create an ask result (requires user confirmation)."""
        return cls(decision="ask", reason=reason)
    
    def is_allowed(self) -> bool:
        """Check if the result allows execution."""
        return self.decision in ("allow", None)
    
    def is_denied(self) -> bool:
        """Check if the result denies execution."""
        return self.decision in ("deny", "block")


@dataclass
class HookDefinition:
    """Hook definition with matcher and configuration."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event: HookEvent = HookEvent.BEFORE_TOOL
    matcher: Optional[str] = None  # Regex pattern to match tool names
    sequential: bool = False  # Execute hooks sequentially vs parallel
    enabled: bool = True
    name: Optional[str] = None
    description: Optional[str] = None
    timeout: float = 60.0  # Timeout in seconds
    
    def matches(self, target: str) -> bool:
        """Check if this hook matches the target (tool name, etc.)."""
        if self.matcher is None:
            return True
        
        import re
        try:
            return bool(re.match(self.matcher, target))
        except re.error:
            # Invalid regex, fall back to simple string match
            return self.matcher in target


@dataclass
class CommandHook(HookDefinition):
    """Hook that executes a shell command."""
    command: str = ""
    shell: bool = True
    env: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.name:
            self.name = f"command_hook_{self.id}"


@dataclass
class FunctionHook(HookDefinition):
    """Hook that executes a Python function."""
    func: Optional[Callable[[HookInput], HookResult]] = None
    is_async: bool = False
    
    def __post_init__(self):
        if not self.name and self.func:
            self.name = self.func.__name__
        elif not self.name:
            self.name = f"function_hook_{self.id}"


@dataclass
class HookExecutionResult:
    """Result of executing a single hook."""
    hook_id: str
    hook_name: str
    event: HookEvent
    success: bool
    output: Optional[HookResult] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hook_id": self.hook_id,
            "hook_name": self.hook_name,
            "event": self.event.value,
            "success": self.success,
            "output": self.output.__dict__ if self.output else None,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "error": self.error
        }


# Type alias for hook functions
HookFunction = Callable[[HookInput], Union[HookResult, None]]
AsyncHookFunction = Callable[[HookInput], Any]  # Returns Awaitable[HookResult]
