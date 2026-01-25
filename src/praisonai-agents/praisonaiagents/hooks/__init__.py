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
- All imports are lazy loaded via centralized _lazy.py utility
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

from .._lazy import create_lazy_getattr_with_groups

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
    "BeforeLLMInput",
    "AfterLLMInput",
    "SessionStartInput",
    "SessionEndInput",
    "OnErrorInput",
    "OnRetryInput",
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
    # Simplified API (beginner-friendly)
    "add_hook",
    "remove_hook",
    "has_hook",
    "get_default_registry",
]

# Grouped lazy imports for DRY and efficient loading
# When one attribute from a group is accessed, all are loaded together
_LAZY_GROUPS = {
    'types_core': {
        'HookEvent': ('praisonaiagents.hooks.types', 'HookEvent'),
        'HookDecision': ('praisonaiagents.hooks.types', 'HookDecision'),
        'HookResult': ('praisonaiagents.hooks.types', 'HookResult'),
        'HookInput': ('praisonaiagents.hooks.types', 'HookInput'),
        'HookOutput': ('praisonaiagents.hooks.types', 'HookOutput'),
    },
    'types_definitions': {
        'HookDefinition': ('praisonaiagents.hooks.types', 'HookDefinition'),
        'CommandHook': ('praisonaiagents.hooks.types', 'CommandHook'),
        'FunctionHook': ('praisonaiagents.hooks.types', 'FunctionHook'),
    },
    'registry': {
        'HookRegistry': ('praisonaiagents.hooks.registry', 'HookRegistry'),
    },
    'runner': {
        'HookRunner': ('praisonaiagents.hooks.runner', 'HookRunner'),
    },
    'events': {
        'BeforeToolInput': ('praisonaiagents.hooks.events', 'BeforeToolInput'),
        'AfterToolInput': ('praisonaiagents.hooks.events', 'AfterToolInput'),
        'BeforeAgentInput': ('praisonaiagents.hooks.events', 'BeforeAgentInput'),
        'AfterAgentInput': ('praisonaiagents.hooks.events', 'AfterAgentInput'),
        'BeforeLLMInput': ('praisonaiagents.hooks.events', 'BeforeLLMInput'),
        'AfterLLMInput': ('praisonaiagents.hooks.events', 'AfterLLMInput'),
        'SessionStartInput': ('praisonaiagents.hooks.events', 'SessionStartInput'),
        'SessionEndInput': ('praisonaiagents.hooks.events', 'SessionEndInput'),
        'OnErrorInput': ('praisonaiagents.hooks.events', 'OnErrorInput'),
        'OnRetryInput': ('praisonaiagents.hooks.events', 'OnRetryInput'),
    },
    'middleware_types': {
        'InvocationContext': ('praisonaiagents.hooks.middleware', 'InvocationContext'),
        'ModelRequest': ('praisonaiagents.hooks.middleware', 'ModelRequest'),
        'ModelResponse': ('praisonaiagents.hooks.middleware', 'ModelResponse'),
        'ToolRequest': ('praisonaiagents.hooks.middleware', 'ToolRequest'),
        'ToolResponse': ('praisonaiagents.hooks.middleware', 'ToolResponse'),
    },
    'middleware_decorators': {
        'before_model': ('praisonaiagents.hooks.middleware', 'before_model'),
        'after_model': ('praisonaiagents.hooks.middleware', 'after_model'),
        'wrap_model_call': ('praisonaiagents.hooks.middleware', 'wrap_model_call'),
        'before_tool': ('praisonaiagents.hooks.middleware', 'before_tool'),
        'after_tool': ('praisonaiagents.hooks.middleware', 'after_tool'),
        'wrap_tool_call': ('praisonaiagents.hooks.middleware', 'wrap_tool_call'),
    },
    'middleware_utilities': {
        'MiddlewareChain': ('praisonaiagents.hooks.middleware', 'MiddlewareChain'),
        'AsyncMiddlewareChain': ('praisonaiagents.hooks.middleware', 'AsyncMiddlewareChain'),
        'MiddlewareManager': ('praisonaiagents.hooks.middleware', 'MiddlewareManager'),
    },
    'verification': {
        'VerificationHook': ('praisonaiagents.hooks.verification', 'VerificationHook'),
        'VerificationResult': ('praisonaiagents.hooks.verification', 'VerificationResult'),
    },
    # Simplified API (beginner-friendly aliases)
    'simplified_api': {
        'add_hook': ('praisonaiagents.hooks.registry', 'add_hook'),
        'remove_hook': ('praisonaiagents.hooks.registry', 'remove_hook'),
        'has_hook': ('praisonaiagents.hooks.registry', 'has_hook'),
        'get_default_registry': ('praisonaiagents.hooks.registry', 'get_default_registry'),
    },
}

# Create the __getattr__ function using centralized utility
__getattr__ = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)
