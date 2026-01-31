"""
Workflows module for PraisonAI Agents.

Provides workflow/pipeline patterns for orchestrating agents and functions.

AgentFlow is the primary class for deterministic pipelines (v1.0+).
Workflow and Pipeline are silent aliases for backward compatibility.
"""

from .workflows import (
    # Core classes
    AgentFlow,  # Primary class (v1.0+)
    Workflow,  # Silent alias for AgentFlow
    Pipeline,  # Silent alias for AgentFlow
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
    TaskContextConfig,
    TaskOutputConfig,
    TaskExecutionConfig,
    TaskRoutingConfig,
    # Enums
    WorkflowOutputPreset,
    TaskExecutionPreset,
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
    "AgentFlow",  # Primary class (v1.0+)
    "Workflow",  # Silent alias for AgentFlow
    "Pipeline",  # Silent alias for AgentFlow
    "Task",
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
    "TaskContextConfig",
    "TaskOutputConfig",
    "TaskExecutionConfig",
    "TaskRoutingConfig",
    
    # Enums
    "WorkflowOutputPreset",
    "TaskExecutionPreset",
    
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
    # Re-export Task from the unified location for backward compatibility
    if name == "Task":
        from praisonaiagents.task import Task
        return Task
    
    if name in _LAZY_IMPORTS:
        module_name = _LAZY_IMPORTS[name]
        import importlib
        module = importlib.import_module(f".{module_name}", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

