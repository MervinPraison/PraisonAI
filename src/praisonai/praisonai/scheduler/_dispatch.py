"""Canonical agent dispatch logic for schedulers."""
from typing import Any
import asyncio


async def adispatch_agent(agent, task: str) -> Any:
    """Canonical 'call this agent with this task' dispatch.

    Prefer the native async entry point; fall back to the sync one in a
    worker thread; otherwise raise a clear error.
    
    Args:
        agent: Agent instance to dispatch to
        task: Task string to execute
        
    Returns:
        Agent execution result
        
    Raises:
        AttributeError: If agent doesn't have start or astart method
    """
    if hasattr(agent, "astart"):
        return await agent.astart(task)
    if hasattr(agent, "start"):
        return await asyncio.to_thread(agent.start, task)
    raise AttributeError(
        f"{type(agent).__name__} must expose either 'start' or 'astart'"
    )