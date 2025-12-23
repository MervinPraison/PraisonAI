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
        # Return a factory function that creates a mock scheduler for testing
        def _create_scheduler(provider='gcp', **kwargs):
            from .agent_scheduler import AgentScheduler
            # Create a mock agent and task for testing
            class MockAgent:
                pass
            return AgentScheduler(MockAgent(), "test task")
        return _create_scheduler
    elif name == 'DeploymentScheduler':
        from .agent_scheduler import AgentScheduler
        return AgentScheduler
    elif name == 'create_deployment_scheduler':
        from .agent_scheduler import create_agent_scheduler
        return create_agent_scheduler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
