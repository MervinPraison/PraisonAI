"""
Hook Types for PraisonAI Agents.

Defines the core types, enums, and dataclasses for the hook system.
"""

import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Union, Literal


class HookEvent(str, Enum):
    """Event names for the hook system.
    
    This enum is also aliased as PluginHook for backward compatibility.
    All plugin lifecycle events are included here for DRY compliance.

    Invariant: every member declared here must have a real emission site, or be
    an explicit alias of a member that does. A member that is neither makes
    ``registry.on(HookEvent.X)`` succeed and then never fire -- silence on a
    plausible-looking registration. ``BEFORE_MESSAGE``, ``AFTER_MESSAGE`` and
    ``TOOL_RESULT_PERSIST`` are aliases (same value => same member); everything
    else is emitted somewhere in the monorepo, which
    ``tests/unit/hooks/test_dead_hook_events.py`` enforces.
    """
    # Plugin/System lifecycle. Emitted by ``PluginManager.register()`` /
    # ``PluginManager.unregister()`` so an observability plugin can watch the
    # plugin set change at runtime (payload: ``PluginLifecycleInput``).
    ON_INIT = "on_init"
    ON_SHUTDOWN = "on_shutdown"
    
    # Tool lifecycle
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    BEFORE_TOOL_DEFINITIONS = "before_tool_definitions"
    
    # Agent lifecycle
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    
    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    # Fired when a durable session write fails (disk-full/corruption/permission).
    # The already-produced turn is spilled to a fallback file and this hook makes
    # the otherwise-silent failure observable for metrics/alerting (Issue #3597).
    SESSION_PERSIST_FAILED = "session_persist_failed"
    
    # LLM lifecycle
    BEFORE_LLM = "before_llm"
    AFTER_LLM = "after_llm"
    # Primary model became unavailable mid-turn and the runtime transparently
    # switched to the next entry in the configured ``fallback_models`` chain.
    # Makes the otherwise silent quality/cost degradation observable so a
    # gateway/plugin can react (notice, alert, metrics) — Issue #3820.
    MODEL_FALLBACK = "model_fallback"

    # Prompt-cache stability (advisory): fired when a turn's cached prompt
    # prefix (model + tool schemas + system-prompt fingerprint) changes from
    # the previous turn, so a long-lived conversation's provider prompt cache
    # will miss. Payload carries the old/new signature and a reason.
    PROMPT_PREFIX_INVALIDATED = "prompt_prefix_invalidated"
    
    # Error handling
    ON_ERROR = "on_error"
    ON_RETRY = "on_retry"
    
    # Message lifecycle (for bot/channel integrations)
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"
    MESSAGE_UNDELIVERED = "message_undelivered"  # Reply permanently undeliverable
    # ``BEFORE_MESSAGE``/``AFTER_MESSAGE`` are *aliases* of the two live events
    # above, not separate slots. The plugin-facing method names
    # ``Plugin.before_message`` / ``Plugin.after_message`` have always routed to
    # MESSAGE_RECEIVED / MESSAGE_SENDING (see ``plugins/manager.py``), so an
    # identically named enum member that nothing emitted meant the obvious
    # registration -- ``@registry.on(HookEvent.BEFORE_MESSAGE)`` -- was silently
    # never called. Same value => same enum member => the registration lands on
    # the event that is actually emitted.
    BEFORE_MESSAGE = "message_received"
    AFTER_MESSAGE = "message_sending"
    
    # Gateway lifecycle
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"
    
    # Compaction (memory management)
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"
    
    # Tool result persistence (for modifying tool results before storage).
    # Alias of AFTER_TOOL: that hook already receives the tool result *before*
    # it is written into the conversation and its in-place rewrite of
    # ``tool_output`` is what gets stored (see ``agent/tool_execution.py``).
    # There is no second persistence chokepoint, so a distinct member could
    # only ever be dead.
    TOOL_RESULT_PERSIST = "after_tool"
    
    # Permission/Config/Auth hooks
    ON_PERMISSION_ASK = "on_permission_ask"
    ON_CONFIG = "on_config"
    ON_AUTH = "on_auth"
    
    # Schedule lifecycle
    SCHEDULE_ADD = "schedule_add"
    SCHEDULE_REMOVE = "schedule_remove"
    SCHEDULE_TRIGGER = "schedule_trigger"

    # CLI backend delegation (subprocess, not LiteLLM HTTP)
    CLI_BACKEND_EXECUTE = "cli_backend_execute"

    # Background job lifecycle. Emitted by BackgroundJobManager when a job
    # reaches a terminal state, so every background job is observable and not
    # only the ones a gateway installed a delivery callback for.
    JOB_COMPLETED = "job_completed"  # A background job finished (ok or error)

    # Kanban task lifecycle. Emitted by the kanban store on each committed
    # transition (it is the chokepoint the CLI, agent tools, dispatcher, HTTP
    # API and UI all write through); the gateway dispatcher additionally emits
    # KANBAN_TASK_MOVED for dependency promotions, which bypass move_task().
    KANBAN_TASK_CREATED = "kanban_task_created"
    KANBAN_TASK_CLAIMED = "kanban_task_claimed"
    KANBAN_TASK_MOVED = "kanban_task_moved"
    KANBAN_TASK_DONE = "kanban_task_done"
    KANBAN_TASK_BLOCKED = "kanban_task_blocked"
    KANBAN_TASK_FAILED = "kanban_task_failed"

    # Claude Code parity events.
    # Emitted when a subagent spawned via ``spawn_subagent`` reaches a terminal
    # state -- synchronous, background, success or failure
    # (see ``tools/subagent_tool.py``; payload: ``SubagentStopInput``).
    SUBAGENT_STOP = "subagent_stop"
    #
    # USER_PROMPT_SUBMIT / NOTIFICATION / SETUP used to be declared here. They
    # were aspirational Claude-Code parity names with no emission site anywhere
    # in this codebase, and registering on one succeeded and then never fired.
    # They are deliberately NOT aliases:
    #   * ``user_prompt_submit`` is not BEFORE_AGENT -- BEFORE_AGENT also fires
    #     for internal/sub-agent invocations no user ever submitted, so an
    #     alias would over-report rather than report.
    #   * there is no notification subsystem to fire ``notification`` from.
    #   * ``setup`` never had a defined meaning at all.
    # Removing them turns a silent no-op into a loud AttributeError (attribute
    # form) or ValueError listing the valid events (string form).

    @classmethod
    def _missing_(cls, value):
        """Resolve legacy string values whose member is now an alias.

        Aliasing ``BEFORE_MESSAGE = "message_received"`` makes the *attribute*
        work, but drops ``"before_message"`` from the value lookup table -- so
        ``HookEvent("before_message")`` (hooks config files, ``add_hook()``
        with a string) would start raising. Map the historical values onto the
        live members instead, so both spellings reach the same emitted event.

        Anything else still raises ``ValueError``: the removed events
        (``user_prompt_submit``, ``notification``, ``setup``) must fail loudly.
        """
        if isinstance(value, str):
            legacy = _LEGACY_EVENT_VALUES.get(value)
            if legacy is not None:
                return cls(legacy)
        return None


# Historical ``HookEvent`` values that are now aliases of a live event.
# Kept resolvable so existing string-based registrations keep working.
_LEGACY_EVENT_VALUES = {
    "before_message": "message_received",
    "after_message": "message_sending",
    "tool_result_persist": "after_tool",
}


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
class KanbanHookInput(HookInput):
    """Hook input for kanban task lifecycle events.
    
    Used by wrapper dispatcher and tools when emitting kanban events.
    Observability adapters can subscribe to these via the hook registry.
    """
    task_id: str = ""
    board: str = "default"
    status: str = ""
    assignee: Optional[str] = field(default=None)
    from_status: Optional[str] = field(default=None)
    to_status: Optional[str] = field(default=None)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result.update({
            "task_id": self.task_id,
            "board": self.board,
            "status": self.status,
            "assignee": self.assignee,
            "from_status": self.from_status,
            "to_status": self.to_status,
        })
        return result


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
