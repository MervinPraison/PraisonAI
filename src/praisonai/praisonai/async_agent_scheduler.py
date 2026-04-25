"""Backward-compatible re-export. Prefer `praisonai.scheduler`.

This module is deprecated. Use the canonical implementation in the
scheduler package for full functionality including async support.
"""

import warnings

warnings.warn(
    "praisonai.async_agent_scheduler is deprecated; "
    "use 'from praisonai.scheduler import AsyncAgentScheduler' instead.",
    DeprecationWarning, stacklevel=2,
)

# TODO: Once AsyncAgentScheduler is moved to scheduler package, import from there
# For now, re-export the existing implementation to avoid breaking changes
from .scheduler.shared import ScheduleParser, backoff_delay, safe_call
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class AsyncAgentExecutorInterface(ABC):
    """Abstract interface for async agent execution."""
    
    @abstractmethod
    async def execute(self, task: str) -> Any:
        """Execute the agent with given task asynchronously."""
        pass


class AsyncPraisonAgentExecutor(AsyncAgentExecutorInterface):
    """Async executor for PraisonAI agents."""
    
    def __init__(self, agent):
        """
        Initialize executor with a PraisonAI agent.
        
        Args:
            agent: PraisonAI Agent instance
        """
        self.agent = agent
        
    async def execute(self, task: str) -> Any:
        """
        Execute the agent with the given task.
        
        Args:
            task: Task description to execute
            
        Returns:
            Agent execution result
        """
        try:
            # Check if agent has async support
            if hasattr(self.agent, 'astart'):
                result = await self.agent.astart(task)
            elif hasattr(self.agent, 'start'):
                # Wrap sync call in executor
                result = await asyncio.to_thread(self.agent.start, task)
            else:
                raise AttributeError("Agent must have either 'start' or 'astart' method")
            return result
        except Exception as e:
            logger.error(f"Async agent execution failed: {e}")
            raise


class AsyncAgentScheduler:
    """
    Async-native scheduler for running PraisonAI agents periodically.
    
    Features:
    - Proper async/await execution
    - Cancellation support  
    - No global state pollution
    - Native async coordination
    
    Example:
        scheduler = AsyncAgentScheduler(agent, task="Check news")
        await scheduler.start(schedule_expr="hourly")
        await asyncio.sleep(3600)  # Let it run
        await scheduler.stop()
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
        Initialize async agent scheduler.
        
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
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._executor = AsyncPraisonAgentExecutor(agent)
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        
    async def start(
        self,
        schedule_expr: str,
        max_retries: int = 3,
        run_immediately: bool = False
    ) -> bool:
        """
        Start scheduled agent execution.
        
        Args:
            schedule_expr: Schedule expression (e.g., "hourly", "*/6h", "3600")
            max_retries: Maximum retry attempts on failure
            run_immediately: If True, run agent immediately before starting schedule
            
        Returns:
            True if scheduler started successfully
        """
        if self.is_running:
            logger.warning("Async scheduler is already running")
            return False
            
        try:
            interval = ScheduleParser.parse(schedule_expr)
            self.is_running = True
            self._stop_event.clear()
            
            logger.info(f"Starting async agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.info(f"Task: {self.task}")
            logger.info(f"Schedule: {schedule_expr} ({interval}s interval)")
            
            # Run immediately if requested
            if run_immediately:
                logger.info("Running agent immediately before starting schedule...")
                await self._execute_with_retry(max_retries)
            
            # Start background task
            self._task = asyncio.create_task(
                self._run_schedule(interval, max_retries)
            )
            
            logger.info("Async agent scheduler started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start async scheduler: {e}")
            self.is_running = False
            return False
    
    async def stop(self) -> bool:
        """
        Stop the scheduler gracefully.
        
        Returns:
            True if stopped successfully
        """
        if not self.is_running:
            logger.info("Async scheduler is not running")
            return True
            
        logger.info("Stopping async agent scheduler...")
        self._stop_event.set()
        
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                logger.warning("Scheduler task didn't stop gracefully, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            
        self.is_running = False
        logger.info("Async agent scheduler stopped")
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
    
    async def _run_schedule(self, interval: int, max_retries: int):
        """Internal method to run scheduled agent executions."""
        while not self._stop_event.is_set():
            logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting async scheduled agent execution")
            
            await self._execute_with_retry(max_retries)
            
            # Wait for next scheduled time or stop event
            logger.info(f"Next execution in {interval} seconds ({interval/3600:.1f} hours)")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break  # Stop event was set
            except asyncio.TimeoutError:
                continue  # Timeout reached, continue with next execution
    
    async def _execute_with_retry(self, max_retries: int):
        """Execute agent with retry logic."""
        self._execution_count += 1
        
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Async attempt {attempt + 1}/{max_retries}")
                result = await self._executor.execute(self.task)
                
                logger.info(f"Async agent execution successful on attempt {attempt + 1}")
                logger.info(f"Result: {result}")
                
                self._success_count += 1
                safe_call(self.on_success, result)
                return
                
            except Exception as e:
                last_exc = e
                logger.error(f"Async agent execution failed on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    wait_time = backoff_delay(attempt)
                    logger.info(f"Waiting {wait_time}s before async retry...")
                    await asyncio.sleep(wait_time)
        
        self._failure_count += 1
        logger.error(f"Async agent execution failed after {max_retries} attempts")
        safe_call(
            self.on_failure,
            last_exc if last_exc is not None
            else RuntimeError(f"Failed after {max_retries} attempts")
        )
    
    async def execute_once(self) -> Any:
        """
        Execute agent immediately (one-time execution).
        
        Returns:
            Agent execution result
        """
        logger.info("Executing agent once (async)")
        try:
            result = await self._executor.execute(self.task)
            logger.info(f"One-time async execution successful: {result}")
            return result
        except Exception as e:
            logger.error(f"One-time async execution failed: {e}")
            raise


def create_async_agent_scheduler(
    agent,
    task: str,
    config: Optional[Dict[str, Any]] = None
) -> AsyncAgentScheduler:
    """
    Factory function to create async agent scheduler.
    
    Args:
        agent: PraisonAI Agent instance
        task: Task description
        config: Optional configuration
        
    Returns:
        Configured AsyncAgentScheduler instance
    """
    return AsyncAgentScheduler(agent, task, config)