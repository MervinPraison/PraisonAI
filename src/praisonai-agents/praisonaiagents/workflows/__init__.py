"""
Workflows module for PraisonAI Agents.

Provides workflow/pipeline patterns for orchestrating agents and functions.
"""

from .workflows import (
    # Core classes
    Workflow,
    Pipeline,  # Alias for Workflow
    WorkflowStep as _OriginalWorkflowStep,  # Keep original for internal use
    WorkflowContext,
    StepResult,
    WorkflowManager,
    
    # Pattern helpers
    Route,
    Parallel,
    Loop,
    Repeat,
    Include,
    If,
    
    # Convenience functions
    route,
    parallel,
    loop,
    repeat,
    include,
    when,
    if_,
    
    # Constants
    MAX_NESTING_DEPTH,
    
    # Backward compatibility aliases
    StepInput,
    StepOutput,
)

from .workflow_configs import (
    # Workflow-level configs
    WorkflowOutputConfig,
    WorkflowPlanningConfig,
    WorkflowMemoryConfig,
    WorkflowHooksConfig,
    # Step-level configs
    WorkflowStepContextConfig,
    WorkflowStepOutputConfig,
    WorkflowStepExecutionConfig,
    WorkflowStepRoutingConfig,
    # Enums
    WorkflowOutputPreset,
    WorkflowStepExecutionPreset,
    # Resolution helpers
    resolve_output_config,
    resolve_planning_config,
    resolve_memory_config,
    resolve_hooks_config,
    resolve_step_context_config,
    resolve_step_output_config,
    resolve_step_execution_config,
    resolve_step_routing_config,
)

__all__ = [
    # Core
    "Workflow",
    "Pipeline",
    "WorkflowStep",
    "WorkflowContext",
    "StepResult",
    "WorkflowManager",
    
    # YAML Parser
    "YAMLWorkflowParser",
    
    # Patterns
    "Route",
    "Parallel",
    "Loop",
    "Repeat",
    "Include",
    "If",
    "route",
    "parallel",
    "loop",
    "repeat",
    "include",
    "when",
    "if_",
    
    # Constants
    "MAX_NESTING_DEPTH",
    
    # Workflow Config Classes
    "WorkflowOutputConfig",
    "WorkflowPlanningConfig",
    "WorkflowMemoryConfig",
    "WorkflowHooksConfig",
    
    # Step Config Classes
    "WorkflowStepContextConfig",
    "WorkflowStepOutputConfig",
    "WorkflowStepExecutionConfig",
    "WorkflowStepRoutingConfig",
    
    # Enums
    "WorkflowOutputPreset",
    "WorkflowStepExecutionPreset",
    
    # Resolution Helpers
    "resolve_output_config",
    "resolve_planning_config",
    "resolve_memory_config",
    "resolve_hooks_config",
    "resolve_step_context_config",
    "resolve_step_output_config",
    "resolve_step_execution_config",
    "resolve_step_routing_config",
    
    # Aliases
    "StepInput",
    "StepOutput",
]


# Lazy imports for heavy modules (YAMLWorkflowParser imports Agent which triggers pydantic/rich)
_LAZY_IMPORTS = {
    "YAMLWorkflowParser": "yaml_parser",
}


def __getattr__(name: str):
    """Lazy import mechanism for heavy modules and deprecation handling."""
    import warnings
    
    # WorkflowStep deprecation - return Task with warning (Phase 4 Consolidation)
    if name == "WorkflowStep":
        warnings.warn(
            "WorkflowStep is deprecated, use Task instead. "
            "Task now supports all WorkflowStep features including action, handler, loop_over, etc. "
            "Example: from praisonaiagents import Task",
            DeprecationWarning,
            stacklevel=2
        )
        from ..task.task import Task
        return Task
    
    if name in _LAZY_IMPORTS:
        module_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

