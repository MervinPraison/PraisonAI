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
    """Input for OnRetry hooks."""
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ""
    operation: str = ""  # tool_call, llm_request, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_message": self.error_message,
            "operation": self.operation
        })
        return base
