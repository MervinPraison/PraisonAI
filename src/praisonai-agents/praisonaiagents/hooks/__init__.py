"""
Hooks Module for PraisonAI Agents.

Provides a powerful hook system for intercepting and modifying agent behavior
at various lifecycle points. Unlike callbacks (which are for UI events),
hooks can intercept, modify, or block tool execution.

Features:
- Event-based hook system (BeforeTool, AfterTool, BeforeAgent, etc.)
- Shell command hooks for external integrations
- Python function hooks for in-process customization
- Matcher patterns for selective hook execution
- Sequential and parallel hook execution
- Decision outcomes (allow, deny, block, ask)

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- Hooks only execute when registered
- No overhead when hooks are disabled

Usage:
    from praisonaiagents.hooks import HookRegistry, HookEvent
    
    # Register a Python function hook
    registry = HookRegistry()
    
    @registry.on(HookEvent.BEFORE_TOOL)
    def my_hook(event_data):
        if event_data.tool_name == "dangerous_tool":
            return HookResult(decision="deny", reason="Tool blocked by policy")
        return HookResult(decision="allow")
    
    # Register a shell command hook
    registry.register_command_hook(
        event=HookEvent.BEFORE_TOOL,
        command="python /path/to/validator.py",
        matcher="write_*"  # Only match tools starting with write_
    )
    
    # Use with Agent
    agent = Agent(
        name="MyAgent",
        hooks=registry
    )
"""

__all__ = [
    # Core types
    "HookEvent",
    "HookDecision",
    "HookResult",
    "HookInput",
    "HookOutput",
    # Hook definitions
    "HookDefinition",
    "CommandHook",
    "FunctionHook",
    # Registry and runner
    "HookRegistry",
    "HookRunner",
    # Event-specific inputs
    "BeforeToolInput",
    "AfterToolInput",
    "BeforeAgentInput",
    "AfterAgentInput",
    "SessionStartInput",
    "SessionEndInput",
    # Middleware types
    "InvocationContext",
    "ModelRequest",
    "ModelResponse",
    "ToolRequest",
    "ToolResponse",
    # Middleware decorators
    "before_model",
    "after_model",
    "wrap_model_call",
    "before_tool",
    "after_tool",
    "wrap_tool_call",
    # Middleware utilities
    "MiddlewareChain",
    "AsyncMiddlewareChain",
    "MiddlewareManager",
    # Verification hooks (protocols)
    "VerificationHook",
    "VerificationResult",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name in ("HookEvent", "HookDecision", "HookResult", "HookInput", "HookOutput"):
        from .types import HookEvent, HookDecision, HookResult, HookInput, HookOutput
        return locals()[name]
    
    if name in ("HookDefinition", "CommandHook", "FunctionHook"):
        from .types import HookDefinition, CommandHook, FunctionHook
        return locals()[name]
    
    if name == "HookRegistry":
        from .registry import HookRegistry
        return HookRegistry
    
    if name == "HookRunner":
        from .runner import HookRunner
        return HookRunner
    
    if name in ("BeforeToolInput", "AfterToolInput", "BeforeAgentInput", 
                "AfterAgentInput", "SessionStartInput", "SessionEndInput"):
        from .events import (
            BeforeToolInput, AfterToolInput, BeforeAgentInput,
            AfterAgentInput, SessionStartInput, SessionEndInput
        )
        return locals()[name]
    
    # Middleware types
    if name in ("InvocationContext", "ModelRequest", "ModelResponse", 
                "ToolRequest", "ToolResponse"):
        from .middleware import (
            InvocationContext, ModelRequest, ModelResponse,
            ToolRequest, ToolResponse
        )
        return locals()[name]
    
    # Middleware decorators
    if name in ("before_model", "after_model", "wrap_model_call",
                "before_tool", "after_tool", "wrap_tool_call"):
        from .middleware import (
            before_model, after_model, wrap_model_call,
            before_tool, after_tool, wrap_tool_call
        )
        return locals()[name]
    
    # Middleware utilities
    if name in ("MiddlewareChain", "AsyncMiddlewareChain", "MiddlewareManager"):
        from .middleware import MiddlewareChain, AsyncMiddlewareChain, MiddlewareManager
        return locals()[name]
    
    # Verification hooks (protocols for autonomy)
    if name in ("VerificationHook", "VerificationResult"):
        from .verification import VerificationHook, VerificationResult
        return locals()[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
