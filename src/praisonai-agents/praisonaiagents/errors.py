"""
Structured exception hierarchy for PraisonAI SDK.

Provides uniform error semantics for consistent handling across:
- Multi-agent orchestration
- Tool execution
- LLM interactions
- Memory operations
- External integrations
"""

from typing import Literal, Protocol, runtime_checkable, Optional, Dict, Any
import uuid


@runtime_checkable
class ErrorContextProtocol(Protocol):
    """Protocol for structured error context propagation."""
    
    agent_id: str
    run_id: str
    is_retryable: bool
    error_category: Literal["tool", "llm", "budget", "validation", "network", "handoff"]


class PraisonAIError(Exception):
    """
    Base error class with structured context for PraisonAI SDK.
    
    All PraisonAI errors inherit from this to ensure uniform error handling,
    context propagation, and observability hooks.
    """
    
    def __init__(
        self, 
        message: str,
        agent_id: str = "unknown",
        run_id: Optional[str] = None,
        error_category: Literal["tool", "llm", "budget", "validation", "network", "handoff"] = "validation",
        is_retryable: bool = False,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.agent_id = agent_id
        self.run_id = run_id or str(uuid.uuid4())
        self.error_category = error_category
        self.is_retryable = is_retryable
        self.context = context or {}

    def __str__(self) -> str:
        return f"[{self.error_category}] {self.message} (agent: {self.agent_id}, run: {self.run_id})"


class ToolExecutionError(PraisonAIError):
    """
    Tool execution failed.
    
    Includes tool name and execution context for better debugging
    and selective retry policies.
    """
    
    def __init__(
        self, 
        message: str, 
        tool_name: str = "unknown",
        agent_id: str = "unknown",
        run_id: Optional[str] = None,
        is_retryable: bool = True,  # Most tool errors are retryable
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        context["tool_name"] = tool_name
        super().__init__(
            message, 
            agent_id=agent_id, 
            run_id=run_id, 
            error_category="tool",
            is_retryable=is_retryable,
            context=context
        )
        self.tool_name = tool_name


class LLMError(PraisonAIError):
    """
    LLM interaction failed.
    
    Distinguishes between rate limits (retryable) vs model errors (fatal).
    """
    
    def __init__(
        self, 
        message: str,
        model_name: str = "unknown", 
        agent_id: str = "unknown",
        run_id: Optional[str] = None,
        is_retryable: bool = False,  # Default to non-retryable unless specified
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        context["model_name"] = model_name
        super().__init__(
            message, 
            agent_id=agent_id, 
            run_id=run_id, 
            error_category="llm",
            is_retryable=is_retryable,
            context=context
        )
        self.model_name = model_name


class BudgetExceededError(PraisonAIError):
    """
    Budget limits exceeded (tokens, time, etc).
    
    Generally not retryable without intervention.
    """
    
    def __init__(
        self, 
        message: str, 
        budget_type: str = "tokens",
        limit: Optional[float] = None,
        used: Optional[float] = None,
        agent_id: str = "unknown",
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        context.update({
            "budget_type": budget_type,
            "limit": limit,
            "used": used
        })
        super().__init__(
            message, 
            agent_id=agent_id, 
            run_id=run_id, 
            error_category="budget",
            is_retryable=False,  # Budget errors require intervention
            context=context
        )
        self.budget_type = budget_type
        self.limit = limit
        self.used = used


class ValidationError(PraisonAIError):
    """
    Input validation failed.
    
    Usually indicates programming errors, not retryable.
    """
    
    def __init__(
        self, 
        message: str,
        field_name: Optional[str] = None, 
        agent_id: str = "unknown",
        run_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        if field_name:
            context["field_name"] = field_name
        super().__init__(
            message, 
            agent_id=agent_id, 
            run_id=run_id, 
            error_category="validation",
            is_retryable=False,  # Validation errors need code fixes
            context=context
        )
        self.field_name = field_name


class NetworkError(PraisonAIError):
    """
    Network/external service error.
    
    Often retryable with backoff.
    """
    
    def __init__(
        self, 
        message: str,
        service_name: str = "unknown",
        status_code: Optional[int] = None,
        agent_id: str = "unknown",
        run_id: Optional[str] = None,
        is_retryable: bool = True,  # Most network errors are retryable
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        context.update({
            "service_name": service_name,
            "status_code": status_code
        })
        super().__init__(
            message, 
            agent_id=agent_id, 
            run_id=run_id, 
            error_category="network",
            is_retryable=is_retryable,
            context=context
        )
        self.service_name = service_name
        self.status_code = status_code


class HandoffError(PraisonAIError):
    """
    Agent handoff/delegation failed.
    
    Includes source/target agent context for multi-agent debugging.
    """
    
    def __init__(
        self, 
        message: str,
        source_agent: str = "unknown",
        target_agent: Optional[str] = None,
        agent_id: str = "unknown",
        run_id: Optional[str] = None,
        is_retryable: bool = False,  # Handoff errors usually need investigation
        context: Optional[Dict[str, Any]] = None
    ):
        context = context or {}
        context.update({
            "source_agent": source_agent,
            "target_agent": target_agent
        })
        super().__init__(
            message, 
            agent_id=agent_id, 
            run_id=run_id, 
            error_category="handoff",
            is_retryable=is_retryable,
            context=context
        )
        self.source_agent = source_agent
        self.target_agent = target_agent


# Specialized handoff errors (maintain backward compatibility)
class HandoffCycleError(HandoffError):
    """Circular handoff dependency detected."""
    
    def __init__(self, message: str, cycle_path: Optional[list] = None, **kwargs):
        super().__init__(message, **kwargs)
        if cycle_path:
            self.context["cycle_path"] = cycle_path


class HandoffDepthError(HandoffError):
    """Maximum handoff depth exceeded."""
    
    def __init__(self, message: str, max_depth: Optional[int] = None, current_depth: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.context.update({
            "max_depth": max_depth,
            "current_depth": current_depth
        })


class HandoffTimeoutError(HandoffError):
    """Handoff operation timed out."""
    
    def __init__(self, message: str, timeout_seconds: Optional[float] = None, **kwargs):
        super().__init__(message, is_retryable=True, **kwargs)  # Timeouts may be retryable
        if timeout_seconds:
            self.context["timeout_seconds"] = timeout_seconds


# Export all error types for easy importing
__all__ = [
    "ErrorContextProtocol",
    "PraisonAIError", 
    "ToolExecutionError",
    "LLMError", 
    "BudgetExceededError",
    "ValidationError", 
    "NetworkError",
    "HandoffError",
    "HandoffCycleError", 
    "HandoffDepthError", 
    "HandoffTimeoutError"
]