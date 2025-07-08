"""
Simplified integration module for adding telemetry to core PraisonAI components.
"""

from typing import Any, Optional, TYPE_CHECKING
from functools import wraps
import time

if TYPE_CHECKING:
    from .telemetry import MinimalTelemetry
    from ..agent.agent import Agent
    from ..task.task import Task
    from ..agents.agents import PraisonAIAgents


def instrument_agent(agent: 'Agent', telemetry: Optional['MinimalTelemetry'] = None):
    """
    Instrument an Agent instance with minimal telemetry.
    
    Args:
        agent: The Agent instance to instrument
        telemetry: Optional telemetry instance (uses global if not provided)
    """
    if not telemetry:
        from .telemetry import get_telemetry
        telemetry = get_telemetry()
    
    if not telemetry.enabled:
        return agent
    
    # Check if agent is already instrumented to avoid double-counting
    if hasattr(agent, '_telemetry_instrumented'):
        return agent
    
    # Store original methods
    original_chat = agent.chat if hasattr(agent, 'chat') else None
    original_start = agent.start if hasattr(agent, 'start') else None
    original_run = agent.run if hasattr(agent, 'run') else None
    original_execute_tool = agent.execute_tool if hasattr(agent, 'execute_tool') else None
    
    # Wrap chat method if it exists (this is the main method called by workflow)
    if original_chat:
        @wraps(original_chat)
        def instrumented_chat(*args, **kwargs):
            try:
                result = original_chat(*args, **kwargs)
                telemetry.track_agent_execution(agent.name, success=True)
                return result
            except Exception as e:
                telemetry.track_agent_execution(agent.name, success=False)
                telemetry.track_error(type(e).__name__)
                raise
        
        agent.chat = instrumented_chat
    
    # Wrap start method if it exists
    if original_start:
        @wraps(original_start)
        def instrumented_start(*args, **kwargs):
            try:
                result = original_start(*args, **kwargs)
                telemetry.track_agent_execution(agent.name, success=True)
                return result
            except Exception as e:
                telemetry.track_agent_execution(agent.name, success=False)
                telemetry.track_error(type(e).__name__)
                raise
        
        agent.start = instrumented_start
    
    # Wrap run method if it exists
    if original_run:
        @wraps(original_run)
        def instrumented_run(*args, **kwargs):
            try:
                result = original_run(*args, **kwargs)
                telemetry.track_agent_execution(agent.name, success=True)
                return result
            except Exception as e:
                telemetry.track_agent_execution(agent.name, success=False)
                telemetry.track_error(type(e).__name__)
                raise
        
        agent.run = instrumented_run
    
    # Wrap execute_tool method
    if original_execute_tool:
        @wraps(original_execute_tool)
        def instrumented_execute_tool(tool_name: str, *args, **kwargs):
            try:
                result = original_execute_tool(tool_name, *args, **kwargs)
                telemetry.track_tool_usage(tool_name, success=True)
                return result
            except Exception as e:
                telemetry.track_tool_usage(tool_name, success=False)
                telemetry.track_error(type(e).__name__)
                raise
        
        agent.execute_tool = instrumented_execute_tool
    
    # Mark agent as instrumented to avoid double instrumentation
    agent._telemetry_instrumented = True
    
    return agent


def instrument_workflow(workflow: 'PraisonAIAgents', telemetry: Optional['MinimalTelemetry'] = None):
    """
    Instrument a PraisonAIAgents workflow with minimal telemetry.
    
    Args:
        workflow: The PraisonAIAgents instance to instrument
        telemetry: Optional telemetry instance (uses global if not provided)
    """
    if not telemetry:
        from .telemetry import get_telemetry
        telemetry = get_telemetry()
    
    if not telemetry.enabled:
        return workflow
    
    # Check if workflow is already instrumented to avoid double-counting
    if hasattr(workflow, '_telemetry_instrumented'):
        return workflow
    
    # Track feature usage
    telemetry.track_feature_usage(f"workflow_{workflow.process}" if hasattr(workflow, 'process') else "workflow")
    
    # Instrument all agents in the workflow
    if hasattr(workflow, 'agents') and workflow.agents:
        for agent in workflow.agents:
            instrument_agent(agent, telemetry)
    
    # Wrap the execute_task method to track task completions
    if hasattr(workflow, 'execute_task'):
        original_execute_task = workflow.execute_task
        
        @wraps(original_execute_task)
        def instrumented_execute_task(task_id, *args, **kwargs):
            task = None
            try:
                # Get task info
                if hasattr(workflow, 'tasks') and isinstance(task_id, int) and task_id < len(workflow.tasks):
                    task = workflow.tasks[task_id]
                
                result = original_execute_task(task_id, *args, **kwargs)
                
                # Track task completion
                task_name = task.name if task and hasattr(task, 'name') else f"task_{task_id}"
                telemetry.track_task_completion(task_name, success=True)
                
                return result
            except Exception as e:
                telemetry.track_error(type(e).__name__)
                if task:
                    task_name = task.name if hasattr(task, 'name') else f"task_{task_id}"
                    telemetry.track_task_completion(task_name, success=False)
                raise
        
        workflow.execute_task = instrumented_execute_task
    
    # Wrap the start method
    original_start = workflow.start
    
    @wraps(original_start)
    def instrumented_start(*args, **kwargs):
        try:
            result = original_start(*args, **kwargs)
            # Don't double-track here since agent.chat already tracks execution
            return result
        except Exception as e:
            telemetry.track_error(type(e).__name__)
            raise
    
    workflow.start = instrumented_start
    
    # Also wrap astart if it exists (async version)
    if hasattr(workflow, 'astart'):
        original_astart = workflow.astart
        
        @wraps(original_astart)
        async def instrumented_astart(*args, **kwargs):
            try:
                result = await original_astart(*args, **kwargs)
                # Don't double-track here since agent.chat already tracks execution
                return result
            except Exception as e:
                telemetry.track_error(type(e).__name__)
                raise
        
        workflow.astart = instrumented_astart
    
    # Mark workflow as instrumented to avoid double instrumentation
    workflow._telemetry_instrumented = True
    
    return workflow


# Auto-instrumentation helper
def auto_instrument_all(telemetry: Optional['MinimalTelemetry'] = None):
    """
    Automatically instrument all new instances of Agent and PraisonAIAgents.
    This should be called after enabling telemetry.
    
    Args:
        telemetry: Optional telemetry instance (uses global if not provided)
    """
    if not telemetry:
        from .telemetry import get_telemetry
        telemetry = get_telemetry()
    
    if not telemetry.enabled:
        return
    
    try:
        # Import the classes
        from ..agent.agent import Agent
        from ..agents.agents import PraisonAIAgents
        
        # Store original __init__ methods
        original_agent_init = Agent.__init__
        original_workflow_init = PraisonAIAgents.__init__
        
        # Wrap Agent.__init__
        @wraps(original_agent_init)
        def agent_init_wrapper(self, *args, **kwargs):
            original_agent_init(self, *args, **kwargs)
            instrument_agent(self, telemetry)
        
        # Wrap PraisonAIAgents.__init__
        @wraps(original_workflow_init)
        def workflow_init_wrapper(self, *args, **kwargs):
            original_workflow_init(self, *args, **kwargs)
            instrument_workflow(self, telemetry)
        
        # Apply wrapped constructors
        Agent.__init__ = agent_init_wrapper
        PraisonAIAgents.__init__ = workflow_init_wrapper
        
    except ImportError:
        # Classes not available, skip auto-instrumentation
        pass