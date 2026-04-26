"""
Agent Scheduler for PraisonAI - Run agents periodically 24/7.

This module provides scheduling capabilities for running PraisonAI agents
at regular intervals, enabling 24/7 autonomous agent operations.

DEPRECATED: This module now imports from unified_agent_scheduler. 
The unified implementation supports both sync and async execution models.

Example:
    # Run news checker every hour
    from praisonai.agent_scheduler import AgentScheduler
    from praisonai_agents import Agent
    
    agent = Agent(
        name="NewsChecker",
        instructions="Check latest AI news and summarize",
        tools=[search_tool]
    )
    
    scheduler = AgentScheduler(agent, task="Check latest AI news")
    scheduler.start(schedule_expr="hourly")
"""

# Import unified implementation - all exports preserved for backward compatibility
from .unified_agent_scheduler import (
    AgentScheduler,
    AgentExecutorInterface, 
    UnifiedPraisonAgentExecutor as PraisonAgentExecutor,
    create_agent_scheduler,
)

# Re-export everything for backward compatibility
__all__ = [
    'AgentScheduler',
    'AgentExecutorInterface',
    'PraisonAgentExecutor', 
    'create_agent_scheduler',
]
