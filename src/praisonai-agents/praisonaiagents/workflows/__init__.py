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
    
    # Aliases
    "StepInput",
    "StepOutput",
]
