"""
Agent Scheduler for PraisonAI - Run agents periodically 24/7.

This module provides scheduling capabilities for running PraisonAI agents
at regular intervals, enabling 24/7 autonomous agent operations.

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

import threading
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ScheduleParser:
    """Parse schedule expressions into intervals."""
    
    @staticmethod
    def parse(schedule_expr: str) -> int:
        """
        Parse schedule expression and return interval in seconds.
        
        Supported formats:
        - "daily" -> 86400 seconds
        - "hourly" -> 3600 seconds
        - "*/30m" -> 1800 seconds (every 30 minutes)
        - "*/1h" -> 3600 seconds (every 1 hour)
        - "60" -> 60 seconds (plain number)
        
        Args:
            schedule_expr: Schedule expression string
            
        Returns:
            Interval in seconds
            
        Raises:
            ValueError: If schedule format is not supported
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


class AgentExecutorInterface(ABC):
    """Abstract interface for agent execution."""
    
    @abstractmethod
    def execute(self, task: str) -> Any:
        """Execute the agent with given task."""
        pass


class PraisonAgentExecutor(AgentExecutorInterface):
    """Executor for PraisonAI agents."""
    
    def __init__(self, agent):
        """
        Initialize executor with a PraisonAI agent.
        
        Args:
            agent: PraisonAI Agent instance
        """
        self.agent = agent
        
    def execute(self, task: str) -> Any:
        """
        Execute the agent with given task.
        
        Args:
            task: Task description for the agent
            
        Returns:
            Agent execution result
        """
        try:
            result = self.agent.start(task)
            return result
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise


class AgentScheduler:
    """
    Scheduler for running PraisonAI agents periodically.
    
    Features:
    - Interval-based scheduling (hourly, daily, custom)
    - Thread-safe operation
    - Automatic retry on failure
    - Execution logging and monitoring
    - Graceful shutdown
    
    Example:
        scheduler = AgentScheduler(agent, task="Check news")
        scheduler.start(schedule_expr="hourly", max_retries=3)
        # Agent runs every hour automatically
        scheduler.stop()  # Stop when needed
    """
    
    def __init__(
        self,
        agent,
        task: str,
        config: Optional[Dict[str, Any]] = None,
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None
    ):
        """
        Initialize agent scheduler.
        
        Args:
            agent: PraisonAI Agent instance
            task: Task description to execute
            config: Optional configuration dict
            on_success: Callback function on successful execution
            on_failure: Callback function on failed execution
        """
        self.agent = agent
        self.task = task
        self.config = config or {}
        self.on_success = on_success
        self.on_failure = on_failure
        
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._executor = PraisonAgentExecutor(agent)
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        
    def start(
        self,
        schedule_expr: str,
        max_retries: int = 3,
        run_immediately: bool = False
    ) -> bool:
        """
        Start scheduled agent execution.
        
        Args:
            schedule_expr: Schedule expression (e.g., "hourly", "*/1h", "3600")
            max_retries: Maximum retry attempts on failure
            run_immediately: If True, run agent immediately before starting schedule
            
        Returns:
            True if scheduler started successfully
        """
        if self.is_running:
            logger.warning("Scheduler is already running")
            return False
            
        try:
            interval = ScheduleParser.parse(schedule_expr)
            self.is_running = True
            self._stop_event.clear()
            
            logger.info(f"Starting agent scheduler: {self.agent.name if hasattr(self.agent, 'name') else 'Agent'}")
            logger.info(f"Task: {self.task}")
            logger.info(f"Schedule: {schedule_expr} ({interval}s interval)")
            logger.info(f"Max retries: {max_retries}")
            
            # Run immediately if requested
            if run_immediately:
                logger.info("Running agent immediately before starting schedule...")
                self._execute_with_retry(max_retries)
            
            self._thread = threading.Thread(
                target=self._run_schedule,
                args=(interval, max_retries),
                daemon=True
            )
            self._thread.start()
            
            logger.info("Agent scheduler started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            self.is_running = False
            return False
    
    def stop(self) -> bool:
        """
        Stop the scheduler gracefully.
        
        Returns:
            True if stopped successfully
        """
        if not self.is_running:
            logger.info("Scheduler is not running")
            return True
            
        logger.info("Stopping agent scheduler...")
        self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
            
        self.is_running = False
        logger.info("Agent scheduler stopped")
        logger.info(f"Execution stats - Total: {self._execution_count}, Success: {self._success_count}, Failed: {self._failure_count}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics.
        
        Returns:
            Dictionary with execution stats
        """
        return {
            "is_running": self.is_running,
            "total_executions": self._execution_count,
            "successful_executions": self._success_count,
            "failed_executions": self._failure_count,
            "success_rate": (self._success_count / self._execution_count * 100) if self._execution_count > 0 else 0
        }
    
    def _run_schedule(self, interval: int, max_retries: int):
        """Internal method to run scheduled agent executions."""
        while not self._stop_event.is_set():
            logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled agent execution")
            
            self._execute_with_retry(max_retries)
            
            # Wait for next scheduled time
            logger.info(f"Next execution in {interval} seconds ({interval/3600:.1f} hours)")
            self._stop_event.wait(interval)
    
    def _execute_with_retry(self, max_retries: int):
        """Execute agent with retry logic."""
        self._execution_count += 1
        success = False
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries}")
                result = self._executor.execute(self.task)
                
                logger.info(f"Agent execution successful on attempt {attempt + 1}")
                logger.info(f"Result: {result}")
                
                self._success_count += 1
                success = True
                
                if self.on_success:
                    self.on_success(result)
                    
                break
                
            except Exception as e:
                logger.error(f"Agent execution failed on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    wait_time = 30 * (attempt + 1)  # Exponential backoff
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
        
        if not success:
            self._failure_count += 1
            logger.error(f"Agent execution failed after {max_retries} attempts")
            
            if self.on_failure:
                self.on_failure(f"Failed after {max_retries} attempts")
    
    def execute_once(self) -> Any:
        """
        Execute agent immediately (one-time execution).
        
        Returns:
            Agent execution result
        """
        logger.info("Executing agent once")
        try:
            result = self._executor.execute(self.task)
            logger.info(f"One-time execution successful: {result}")
            return result
        except Exception as e:
            logger.error(f"One-time execution failed: {e}")
            raise


def create_agent_scheduler(
    agent,
    task: str,
    config: Optional[Dict[str, Any]] = None
) -> AgentScheduler:
    """
    Factory function to create agent scheduler.
    
    Args:
        agent: PraisonAI Agent instance
        task: Task description
        config: Optional configuration
        
    Returns:
        Configured AgentScheduler instance
    """
    return AgentScheduler(agent, task, config)
