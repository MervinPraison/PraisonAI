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


class ScheduleParser:
    """Parse schedule expressions into intervals in seconds."""
    
    @staticmethod
    def parse(schedule_expr: str) -> int:
        """
        Parse schedule expression and return interval in seconds.
        
        Supported formats:
        - "daily" -> 86400 seconds
        - "hourly" -> 3600 seconds
        - "*/30m" -> 1800 seconds (every 30 minutes)
        - "*/6h" -> 21600 seconds (every 6 hours)
        - "*/30s" -> 30 seconds (every 30 seconds)
        - "3600" -> 3600 seconds (plain number)
        
        Args:
            schedule_expr: Schedule expression string
            
        Returns:
            Interval in seconds
            
        Raises:
            ValueError: If schedule format is not supported
            
        Examples:
            >>> ScheduleParser.parse("hourly")
            3600
            >>> ScheduleParser.parse("*/30m")
            1800
            >>> ScheduleParser.parse("daily")
            86400
        """
        schedule_expr = schedule_expr.strip().lower()
        
        if schedule_expr == "daily":
            return 86400
        elif schedule_expr == "hourly":
            return 3600
        elif schedule_expr.isdigit():
            return int(schedule_expr)
        elif schedule_expr.startswith("*/"):
            interval_part = schedule_expr[2:]
            if interval_part.endswith("m"):
                minutes = int(interval_part[:-1])
                return minutes * 60
            elif interval_part.endswith("h"):
                hours = int(interval_part[:-1])
                return hours * 3600
            elif interval_part.endswith("s"):
                return int(interval_part[:-1])
            else:
                return int(interval_part)
        else:
            raise ValueError(f"Unsupported schedule format: {schedule_expr}")


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
