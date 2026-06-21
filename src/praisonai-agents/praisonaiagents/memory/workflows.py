"""
Backward compatibility shim for workflows.

All workflow functionality has been moved to praisonaiagents.workflows.
This module provides re-exports to maintain backward compatibility.
"""

from ..workflows.workflows import (  # noqa: F401
    Workflow,
    WorkflowManager,
    WorkflowContext,
    StepResult,
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

# Import Task from its actual location
from ..task.task import Task  # noqa: F401

# Backward compatibility aliases
Pipeline = Workflow
StepInput = WorkflowContext
StepOutput = StepResult