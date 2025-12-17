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

__all__ = [
    # Core
    "Workflow",
    "Pipeline",
    "WorkflowStep",
    "WorkflowContext",
    "StepResult",
    "WorkflowManager",
    
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
