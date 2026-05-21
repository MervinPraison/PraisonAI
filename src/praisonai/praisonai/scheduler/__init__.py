"""
PraisonAI Scheduler Module

This module provides scheduling capabilities for running agents and deployments
at regular intervals, enabling 24/7 autonomous operations.

Components:
- ScheduleParser: Parse schedule expressions (hourly, daily, */30m, etc.)
- ExecutorInterface: Abstract interface for executors
- AgentScheduler: Schedule agent execution at regular intervals
- DeploymentScheduler: Schedule deployment operations
"""

from .base import ScheduleParser, ExecutorInterface, PraisonAgentExecutor

__all__ = [
    'ScheduleParser',
    'ExecutorInterface',
    'PraisonAgentExecutor',
    'ScheduledAgentExecutor',
    'JobResult',
]

# Lazy imports for modules that will be created later
def __getattr__(name):
    if name == 'AgentScheduler':
        from .agent_scheduler import AgentScheduler
        return AgentScheduler
    elif name == 'create_agent_scheduler':
        from .agent_scheduler import create_agent_scheduler
        return create_agent_scheduler
    elif name == 'create_scheduler':
        # Return the real deployment scheduler factory
        from .deployment import create_deployment_scheduler
        return create_deployment_scheduler
    elif name == 'DeploymentScheduler':
        from .deployment import DeploymentScheduler
        return DeploymentScheduler
    elif name == 'create_deployment_scheduler':
        from .deployment import create_deployment_scheduler
        return create_deployment_scheduler
    elif name in ('ScheduledAgentExecutor', 'JobResult'):
        from .executor import ScheduledAgentExecutor, JobResult
        return ScheduledAgentExecutor if name == 'ScheduledAgentExecutor' else JobResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
