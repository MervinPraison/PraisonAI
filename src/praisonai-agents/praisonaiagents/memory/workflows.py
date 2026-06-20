"""
Backward-compatible re-export for workflows.

Canonical workflow engine now lives in praisonaiagents.workflows.workflows.
This file is preserved for backward compatibility with existing imports.
"""

# Re-export all workflow symbols from the canonical location
from ..workflows.workflows import (  # noqa: F401
    WorkflowContext,
    StepResult,
    Workflow,
    WorkflowManager,
    Route,
    Parallel,
    Loop,
    Repeat,
    route,
    parallel,
    loop,
    repeat,
    create_workflow_manager,
)

# Import Task from its module
from ..task.task import Task  # noqa: F401

# Backward compatibility aliases
StepInput = WorkflowContext
StepOutput = StepResult

__all__ = [
    "WorkflowContext",
    "StepResult", 
    "StepInput",
    "StepOutput",
    "Workflow",
    "WorkflowManager",
    "Task",
    "Route",
    "Parallel",
    "Loop",
    "Repeat",
    "route",
    "parallel",
    "loop",
    "repeat",
    "create_workflow_manager",
]