"""
Base components for PraisonAI Scheduler.

This module provides shared functionality for all schedulers:
- ScheduleParser: Parse schedule expressions into intervals
- ExecutorInterface: Abstract interface for executors
- PraisonAgentExecutor: Executor for PraisonAI agents
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


from .shared import ScheduleParser  # noqa: F401 — canonical definition lives in shared.py


class ExecutorInterface(ABC):
    """Abstract interface for executors."""
    
    @abstractmethod
    def execute(self, task: str) -> Any:
        """
        Execute a task.
        
        Args:
            task: Task description or instruction
            
        Returns:
            Execution result
            
        Raises:
            Exception: If execution fails
        """
        pass


class PraisonAgentExecutor(ExecutorInterface):
    """Executor for PraisonAI agents."""
    
    def __init__(self, agent):
        """
        Initialize executor with a PraisonAI agent.
        
        Args:
            agent: PraisonAI Agent instance (must have start() method)
        """
        self.agent = agent
        
    def execute(self, task: str) -> Any:
        """
        Execute the agent with given task.
        
        Args:
            task: Task description for the agent
            
        Returns:
            Agent execution result
            
        Raises:
            Exception: If agent execution fails
        """
        try:
            result = self.agent.start(task)
            return result
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise
