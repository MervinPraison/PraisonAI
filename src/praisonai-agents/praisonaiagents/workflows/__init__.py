"""
Workflows module for PraisonAI Agents.

Provides workflow/pipeline patterns for orchestrating agents and functions.
"""

from .workflows import (
    # Core classes
    Workflow,
    Pipeline,  # Alias for Workflow
    WorkflowStep,
    WorkflowContext,
    StepResult,
    WorkflowManager,
    
    # Pattern helpers
    Route,
    Parallel,
    Loop,
    Repeat,
    
    # Convenience functions
    route,
    parallel,
    loop,
    repeat,
    
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

from .yaml_parser import YAMLWorkflowParser

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
    "route",
    "parallel",
    "loop",
    "repeat",
    
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
