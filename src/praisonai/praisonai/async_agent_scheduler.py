"""
Async-native agent scheduler for PraisonAI.

DEPRECATED: This module now imports from unified_agent_scheduler.
The unified implementation supports both sync and async execution models with 
proper loop binding and cancellation.

Use AgentScheduler.astart() for async execution instead of AsyncAgentScheduler.start().
"""

# Import unified implementation with async interface mapped
from .unified_agent_scheduler import (
    AgentScheduler,
    AsyncAgentExecutorInterface,
    UnifiedPraisonAgentExecutor as AsyncPraisonAgentExecutor,
)


class AsyncAgentScheduler:
    """
    DEPRECATED: Wrapper around unified AgentScheduler for backward compatibility.
    
    New code should use AgentScheduler with astart()/astop() methods.
    """
    
    def __init__(self, *args, **kwargs):
        """Initialize with unified AgentScheduler."""
        self._scheduler = AgentScheduler(*args, **kwargs)
        
    async def start(self, *args, **kwargs):
        """Start async scheduling (deprecated, use AgentScheduler.astart)."""
        return await self._scheduler.astart(*args, **kwargs)
        
    async def stop(self):
        """Stop async scheduling (deprecated, use AgentScheduler.astop)."""
        return await self._scheduler.astop()
        
    async def get_stats(self):
        """Get stats (deprecated, use AgentScheduler.aget_stats)."""
        return await self._scheduler.aget_stats()
        
    @property
    def agent(self):
        return self._scheduler.agent
        
    @property 
    def task(self):
        return self._scheduler.task
        
    @property
    def config(self):
        return self._scheduler.config


# Re-export everything for backward compatibility
__all__ = [
    'AsyncAgentScheduler',
    'AsyncAgentExecutorInterface', 
    'AsyncPraisonAgentExecutor',
]