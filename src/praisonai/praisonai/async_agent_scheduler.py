"""
Async-native agent scheduler for PraisonAI.

Replaces the daemon thread-based scheduler with proper async execution
that supports cancellation and doesn't use process-global state.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class AsyncScheduleParser:
    """Parse schedule expressions into intervals for async execution."""
    
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
            # Use the agent's async start method if available, otherwise run_until_complete
            if hasattr(self.agent, 'astart'):
                result = await self.agent.astart(task)
            elif hasattr(self.agent, 'start'):
                # Run sync method in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, self.agent.start, task)
            else:
                raise AttributeError("Agent does not have start() or astart() method")
                
            logger.info(f"Agent execution completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise


class AsyncAgentScheduler:
    """
    Async-native agent scheduler that replaces daemon threads with proper
    async execution and cooperative cancellation.
    """
    
    def __init__(
        self,
        agent: Any,
        task: str,
        config: Optional[Dict[str, Any]] = None,
        on_success: Optional[Callable[[Any], None]] = None,
        on_failure: Optional[Callable[[Exception], None]] = None
    ):
        """
        Initialize async agent scheduler.
        
        Args:
            agent: Agent instance to schedule
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
        
        self._is_running = False
        self._cancel_event = asyncio.Event()
        self._task_handle: Optional[asyncio.Task] = None
        self._executor = AsyncPraisonAgentExecutor(agent)
        
        # Thread-safe counters using asyncio.Lock
        self._execution_count = 0
        self._success_count = 0  
        self._failure_count = 0
        self._stats_lock = asyncio.Lock()
        
    async def start(
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
        if self._is_running:
            logger.warning("Scheduler is already running")
            return False
            
        try:
            interval = AsyncScheduleParser.parse(schedule_expr)
            self._is_running = True
            self._cancel_event.clear()
            
            logger.info(f"Starting async agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.info(f"Task: {self.task}")
            logger.info(f"Schedule: {schedule_expr} ({interval}s interval)")
            logger.info(f"Max retries: {max_retries}")
            
            # Run immediately if requested
            if run_immediately:
                logger.info("Running agent immediately before starting schedule...")
                await self._execute_with_retry(max_retries)
            
            # Start the async scheduling task
            self._task_handle = asyncio.create_task(
                self._run_schedule(interval, max_retries)
            )
            
            logger.info("Async agent scheduler started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            self._is_running = False
            return False
    
    async def stop(self) -> bool:
        """
        Stop the scheduler gracefully with proper cancellation.
        
        Returns:
            True if stopped successfully
        """
        if not self._is_running:
            logger.info("Scheduler is not running")
            return True
            
        logger.info("Stopping async agent scheduler...")
        self._cancel_event.set()
        
        if self._task_handle:
            try:
                # Wait for the current execution to complete or cancel
                await asyncio.wait_for(self._task_handle, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Scheduler did not stop gracefully, cancelling...")
                self._task_handle.cancel()
                try:
                    await self._task_handle
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            
        self._is_running = False
        async with self._stats_lock:
            logger.info("Async agent scheduler stopped")
            logger.info(f"Execution stats - Total: {self._execution_count}, "
                       f"Success: {self._success_count}, Failed: {self._failure_count}")
        return True
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics in a thread-safe manner.
        
        Returns:
            Dictionary with execution stats
        """
        async with self._stats_lock:
            return {
                "is_running": self._is_running,
                "execution_count": self._execution_count,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "agent_name": getattr(self.agent, 'name', 'Agent'),
                "task": self.task
            }
    
    async def _run_schedule(self, interval: int, max_retries: int) -> None:
        """
        Main scheduling loop with cooperative cancellation.
        
        Args:
            interval: Execution interval in seconds
            max_retries: Maximum retry attempts
        """
        try:
            while not self._cancel_event.is_set():
                try:
                    await self._execute_with_retry(max_retries)
                except asyncio.CancelledError:
                    logger.info("Scheduler execution cancelled")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in scheduler loop: {e}")
                
                # Wait for next execution or cancellation
                try:
                    await asyncio.wait_for(self._cancel_event.wait(), timeout=interval)
                    # If we get here, cancellation was requested
                    break
                except asyncio.TimeoutError:
                    # Timeout is expected - continue to next execution
                    continue
                    
        except asyncio.CancelledError:
            logger.info("Schedule loop cancelled")
        finally:
            self._is_running = False
    
    async def _execute_with_retry(self, max_retries: int) -> None:
        """
        Execute agent task with retry logic.
        
        Args:
            max_retries: Maximum number of retry attempts
        """
        async with self._stats_lock:
            self._execution_count += 1
            
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Executing agent task (attempt {attempt + 1}/{max_retries + 1})")
                result = await self._executor.execute(self.task)
                
                async with self._stats_lock:
                    self._success_count += 1
                    
                if self.on_success:
                    try:
                        self.on_success(result)
                    except Exception as e:
                        logger.error(f"Error in success callback: {e}")
                        
                logger.info("Agent task executed successfully")
                return
                
            except asyncio.CancelledError:
                logger.info("Agent execution cancelled")
                raise
            except Exception as e:
                logger.error(f"Agent execution failed on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    # Final attempt failed
                    async with self._stats_lock:
                        self._failure_count += 1
                        
                    if self.on_failure:
                        try:
                            self.on_failure(e)
                        except Exception as callback_error:
                            logger.error(f"Error in failure callback: {callback_error}")
                    break
                else:
                    # Wait before retry (with cancellation support)
                    try:
                        await asyncio.wait_for(
                            self._cancel_event.wait(), 
                            timeout=min(2 ** attempt, 60)  # Exponential backoff, max 60s
                        )
                        # If we get here, cancellation was requested
                        raise asyncio.CancelledError()
                    except asyncio.TimeoutError:
                        # Timeout is expected - continue to retry
                        continue