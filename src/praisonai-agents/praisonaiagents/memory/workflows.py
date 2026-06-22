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

# Re-export structured result types that were previously accessible via this module
from ..workflows.results import (  # noqa: F401
    StepError,
    WorkflowResult,
    StepStatus,
    ErrorStrategy,
)

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
    "StepError",
    "WorkflowResult",
    "StepStatus",
    "ErrorStrategy",
]