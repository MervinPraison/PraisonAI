"""
Backward compatibility shim for workflows.

All workflow functionality has been moved to praisonaiagents.workflows.
This module provides re-exports to maintain backward compatibility.
"""

from ..workflows.workflows import (  # noqa: F401
    Workflow as _Workflow,
    WorkflowManager,
    WorkflowContext,
    StepResult,
    StepInput,  # Already defined in canonical module
    StepOutput,  # Already defined in canonical module
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


class Workflow(_Workflow):
    """
    Backward compatibility wrapper for Workflow class.
    
    Maps old constructor parameters to new AgentFlow parameters:
    - default_llm -> llm
    - planning_llm -> planning (as part of config)
    - memory_config -> memory
    """
    
    def __init__(self, **kwargs):
        # Map old parameter names to new ones
        if 'default_llm' in kwargs:
            kwargs['llm'] = kwargs.pop('default_llm')
        
        if 'planning_llm' in kwargs:
            # Convert planning_llm to planning config
            from ..workflows.workflow_configs import WorkflowPlanningConfig
            planning_llm = kwargs.pop('planning_llm')
            # Check if planning config already exists
            if 'planning' in kwargs and isinstance(kwargs['planning'], WorkflowPlanningConfig):
                kwargs['planning'].llm = planning_llm
            elif 'planning' in kwargs and kwargs['planning'] is True:
                # Replace bool with config
                kwargs['planning'] = WorkflowPlanningConfig(llm=planning_llm, enabled=True)
            elif 'planning' not in kwargs:
                # Create new config
                kwargs['planning'] = WorkflowPlanningConfig(llm=planning_llm, enabled=True)
        
        if 'memory_config' in kwargs:
            # Convert memory_config to memory
            memory_config = kwargs.pop('memory_config')
            if isinstance(memory_config, dict):
                # Try to create a WorkflowMemoryConfig if it looks like one
                from ..workflows.workflow_configs import WorkflowMemoryConfig
                try:
                    # If it has the right structure, convert to WorkflowMemoryConfig
                    valid_keys = {'backend', 'user_id', 'session_id', 'config'}
                    if any(k in memory_config for k in valid_keys):
                        # Filter to only valid keys
                        filtered = {k: v for k, v in memory_config.items() if k in valid_keys}
                        kwargs['memory'] = WorkflowMemoryConfig(**filtered)
                    else:
                        # Old memory_config format not compatible with new structure
                        # Don't pass it through to avoid validation errors
                        # The old implementation had different memory structure
                        pass
                except Exception:
                    # If conversion fails, don't pass it through
                    pass
            elif memory_config is not None:
                # Non-dict memory config (could be bool or instance)
                kwargs['memory'] = memory_config
        
        # Call parent constructor
        super().__init__(**kwargs)


# Backward compatibility aliases
Pipeline = Workflow


# Export all symbols
__all__ = [
    "Workflow",
    "WorkflowManager",
    "WorkflowContext",
    "StepResult",
    "StepInput",
    "StepOutput",
    "Route",
    "Parallel",
    "Loop",
    "Repeat",
    "route",
    "parallel",
    "loop",
    "repeat",
    "create_workflow_manager",
    "Task",
    "Pipeline",
]