"""
Event-specific input types for the hook system.

Each event type has its own input class with relevant fields.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from .types import HookInput


@dataclass
class BeforeToolInput(HookInput):
    """Input for BeforeTool hooks."""
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_description": self.tool_description
        })
        return base


@dataclass
class AfterToolInput(HookInput):
    """Input for AfterTool hooks."""
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_output: Any = None
    tool_error: Optional[str] = None
    execution_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": str(self.tool_output) if self.tool_output else None,
            "tool_error": self.tool_error,
            "execution_time_ms": self.execution_time_ms
        })
        return base


@dataclass
class BeforeToolDefinitionsInput(HookInput):
    """Input for BeforeToolDefinitions hooks.

    Fired right after the advertised tool definitions are assembled for a
    request and before they reach the LLM. Hooks should modify or filter the
    ``tool_definitions`` list in place (e.g. ``data.tool_definitions[:] = ...``)
    to redact parameters, append usage guidance to descriptions, or constrain
    the advertised schema per request. This mirrors how BEFORE_LLM mutates its
    payload in place; only in-place mutations are adopted by the runtime.
    """
    tool_definitions: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "tool_definitions_count": len(self.tool_definitions),
            "model": self.model,
        })
        return base


@dataclass
class BeforeAgentInput(HookInput):
    """Input for BeforeAgent hooks."""
    prompt: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    tools_available: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "prompt": self.prompt,
            "conversation_history_length": len(self.conversation_history),
            "tools_available": self.tools_available
        })
        return base


@dataclass
class AfterAgentInput(HookInput):
    """Input for AfterAgent hooks."""
    prompt: str = ""
    response: str = ""
    tools_used: List[str] = field(default_factory=list)
    total_tokens: int = 0
    execution_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "prompt": self.prompt,
            "response": self.response[:500] if self.response else "",  # Truncate for JSON
            "tools_used": self.tools_used,
            "total_tokens": self.total_tokens,
            "execution_time_ms": self.execution_time_ms
        })
        return base


@dataclass
class SessionStartInput(HookInput):
    """Input for SessionStart hooks."""
    source: str = "startup"  # startup, resume, clear
    session_name: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "source": self.source,
            "session_name": self.session_name
        })
        return base


@dataclass
class SessionEndInput(HookInput):
    """Input for SessionEnd hooks."""
    reason: str = "exit"  # exit, clear, logout, error
    total_turns: int = 0
    total_tokens: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "reason": self.reason,
            "total_turns": self.total_turns,
            "total_tokens": self.total_tokens
        })
        return base


@dataclass
class BeforeLLMInput(HookInput):
    """Input for BeforeLLM hooks."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "messages_count": len(self.messages),
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        })
        return base


@dataclass
class AfterLLMInput(HookInput):
    """Input for AfterLLM hooks."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    response: str = ""
    model: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "messages_count": len(self.messages),
            "response_length": len(self.response),
            "model": self.model,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms
        })
        return base


@dataclass
class OnErrorInput(HookInput):
    """Input for OnError hooks."""
    error_type: str = ""
    error_message: str = ""
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "error_type": self.error_type,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "context": self.context
        })
        return base


@dataclass
class OnRetryInput(HookInput):
    """Input for OnRetry hooks fired during tool execution retries."""
    tool_name: str = ""
    attempt: int = 1  # Current attempt number (1-based)
    delay_ms: int = 0
    error: str = ""
    max_attempts: int = 0
    error_type: str = "unknown"
    # Legacy fields for backward compatibility
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ""
    operation: str = ""  # tool_call, llm_request, etc.
    delay_seconds: float = 0.0  # Delay before retry
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "tool_name": self.tool_name,
            "attempt": self.attempt,
            "delay_ms": self.delay_ms,
            "error": self.error,
            "max_attempts": self.max_attempts,
            "error_type": self.error_type,
            # Legacy fields
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "operation": self.operation,
            "delay_seconds": self.delay_seconds
        })
        return base


@dataclass
class MessageReceivedInput(HookInput):
    """Input for MESSAGE_RECEIVED hooks (bot received an incoming message)."""
    platform: str = ""
    content: str = ""
    sender_id: str = ""
    channel_id: str = ""
    channel_type: str = ""
    message_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "platform": self.platform,
            "content": self.content[:500] if self.content else "",
            "sender_id": self.sender_id,
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "message_id": self.message_id,
        })
        return base


@dataclass
class MessageSendingInput(HookInput):
    """Input for MESSAGE_SENDING hooks (bot about to send a message).
    
    Hooks can modify content or cancel the send by returning
    HookResult with decision=DENY.
    """
    platform: str = ""
    content: str = ""
    channel_id: str = ""
    reply_to: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "platform": self.platform,
            "content": self.content[:500] if self.content else "",
            "channel_id": self.channel_id,
            "reply_to": self.reply_to,
        })
        return base


@dataclass
class MessageSentInput(HookInput):
    """Input for MESSAGE_SENT hooks (bot successfully sent a message)."""
    platform: str = ""
    content: str = ""
    channel_id: str = ""
    message_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "platform": self.platform,
            "content": self.content[:500] if self.content else "",
            "channel_id": self.channel_id,
            "message_id": self.message_id,
        })
        return base


@dataclass
class MessageUndeliveredInput(HookInput):
    """Input for MESSAGE_UNDELIVERED hooks (a reply could not be delivered).

    Fired by the gateway when an outbound reply fails *permanently* (the target
    was confirmed dead, or delivery exhausted its retries) so operators can
    route the failure — mirror it to a home channel, alert, or re-queue —
    without patching adapters. It is a notification only: the reply has already
    been parked in the DLQ (when configured) and, best-effort, a short plain-text
    notice may have been attempted on the same channel.
    """
    platform: str = ""
    content: str = ""
    channel_id: str = ""
    error: str = ""
    notice_delivered: bool = False

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "platform": self.platform,
            "content": self.content[:500] if self.content else "",
            "channel_id": self.channel_id,
            "error": self.error,
            "notice_delivered": self.notice_delivered,
        })
        return base


@dataclass
class GatewayStartInput(HookInput):
    """Input for GATEWAY_START hooks (gateway/BotOS started)."""
    platforms: List[str] = field(default_factory=list)
    bot_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "platforms": self.platforms,
            "bot_count": self.bot_count,
        })
        return base


@dataclass
class GatewayStopInput(HookInput):
    """Input for GATEWAY_STOP hooks (gateway/BotOS stopped)."""
    platforms: List[str] = field(default_factory=list)
    bot_count: int = 0
    reason: str = "stop"
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "platforms": self.platforms,
            "bot_count": self.bot_count,
            "reason": self.reason,
        })
        return base


@dataclass
class CliBackendExecuteInput(HookInput):
    """Input for CLI_BACKEND_EXECUTE hooks (agent delegated a turn to a CLI backend)."""
    backend: str = ""
    command: Optional[List[Any]] = None
    content: Optional[str] = None
    error: Optional[str] = None
    transport: str = "subprocess"
    praisonai_llm_http: bool = False

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "backend": self.backend,
            "command": self.command,
            "content": self.content[:500] if self.content else None,
            "error": self.error,
            "transport": self.transport,
            "praisonai_llm_http": self.praisonai_llm_http,
        })
        return base


@dataclass
class ScheduleTriggerInput(HookInput):
    """Input for SCHEDULE_TRIGGER hooks (a scheduled job fired)."""
    job_name: str = ""
    job_id: str = ""
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "job_name": self.job_name,
            "job_id": self.job_id,
            "message": self.message[:500] if self.message else "",
        })
        return base


@dataclass
class JobCompletedInput(HookInput):
    """Input for JOB_COMPLETED hooks (a background job finished).

    Emitted when a background subagent/job launched via
    ``spawn_subagent(background=True)`` reaches a terminal state
    (completed or failed). Carries the optional origin/delivery context
    captured at spawn time so a gateway can route the result back to the
    originating conversation without an active turn.
    """
    job_id: str = ""
    status: str = ""
    result: Any = None
    error: Optional[str] = None
    deliver: str = ""
    platform: str = ""
    chat_id: str = ""
    thread_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "job_id": self.job_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "deliver": self.deliver,
            "platform": self.platform,
            "chat_id": self.chat_id,
            "thread_id": self.thread_id,
        })
        return base
