"""
Unified Agent Scheduler for PraisonAI - Single implementation for sync and async.

This module consolidates the previous separate sync/async scheduler implementations
into a single AgentScheduler class that supports both execution models safely.
"""

import asyncio
import logging
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Union
from abc import ABC, abstractmethod

from .scheduler.shared import ScheduleParser, backoff_delay, safe_call

logger = logging.getLogger(__name__)


class AgentExecutorInterface(ABC):
    """Abstract interface for agent execution."""
    
    @abstractmethod
    def execute(self, task: str) -> Any:
        """Execute the agent with given task."""
        pass


class AsyncAgentExecutorInterface(ABC):
    """Abstract interface for async agent execution."""
    
    @abstractmethod
    async def aexecute(self, task: str) -> Any:
        """Execute the agent with given task asynchronously."""
        pass


class UnifiedPraisonAgentExecutor(AgentExecutorInterface, AsyncAgentExecutorInterface):
    """Unified executor that supports both sync and async execution."""
    
    def __init__(self, agent):
        """
        Initialize executor with a PraisonAI agent.
        
        Args:
            agent: PraisonAI Agent instance
        """
        self.agent = agent
        
    def execute(self, task: str) -> Any:
        """
        Execute the agent with given task (sync).
        
        Args:
            task: Task description for the agent
            
        Returns:
            Agent execution result
        """
        try:
            if hasattr(self.agent, 'start'):
                result = self.agent.start(task)
            else:
                raise AttributeError("Agent does not have start() method")
            return result
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise

    async def aexecute(self, task: str) -> Any:
        """
        Execute the agent with given task (async).
        
        Args:
            task: Task description for the agent
            
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
                
            return result
        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            raise


class AgentScheduler:
    """
    Unified scheduler for running PraisonAI agents periodically.
    
    Supports both sync and async execution models with proper loop binding
    and cancellation. Replaces the previous dual implementation with a 
    single source of truth.
    
    Features:
    - Interval-based scheduling (hourly, daily, custom)
    - Thread-safe operation
    - Async-safe with proper loop binding
    - Automatic retry on failure
    - Execution logging and monitoring
    - Graceful shutdown
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
        
        # State management
        self._is_running = False
        self._executor = UnifiedPraisonAgentExecutor(agent)
        
        # Stats
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._stats_lock = threading.Lock()
        
        # Sync/async coordination
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._cancel_event: Optional[asyncio.Event] = None
        self._task_handle: Optional[asyncio.Task] = None
        self._stop_event: Optional[threading.Event] = None
        self._thread: Optional[threading.Thread] = None
        self._init_lock = threading.Lock()

    def _bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Bind async primitives to a specific event loop."""
        with self._init_lock:
            if self._loop is loop:
                return
            if self._loop is not None and self._loop is not loop:
                raise RuntimeError(
                    "AgentScheduler already bound to a different event loop; "
                    "call .reset() before reusing in a new loop."
                )
            self._loop = loop
            self._cancel_event = asyncio.Event()

    def reset(self) -> None:
        """Reset the scheduler to be reusable in a different event loop."""
        if self._is_running:
            raise RuntimeError("Cannot reset while scheduler is running")
        
        with self._init_lock:
            self._loop = None
            self._cancel_event = None
            self._task_handle = None
            self._stop_event = None
            self._thread = None

    # Sync interface
    def start(
        self,
        schedule_expr: str,
        max_retries: int = 3,
        run_immediately: bool = False
    ) -> bool:
        """
        Start scheduled agent execution (sync).
        
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
            interval = ScheduleParser.parse(schedule_expr)
            self._is_running = True
            self._stop_event = threading.Event()
            
            logger.info(f"Starting agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.info(f"Task: {self.task}")
            logger.info(f"Schedule: {schedule_expr} ({interval}s interval)")
            logger.info(f"Max retries: {max_retries}")
            
            # Run immediately if requested
            if run_immediately:
                logger.info("Running agent immediately before starting schedule...")
                self._execute_with_retry_sync(max_retries)
            
            self._thread = threading.Thread(
                target=self._run_schedule_sync,
                args=(interval, max_retries),
                daemon=True
            )
            self._thread.start()
            
            logger.info("Agent scheduler started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            self._is_running = False
            return False

    def stop(self) -> bool:
        """
        Stop the scheduler gracefully (sync).
        
        Returns:
            True if stopped successfully
        """
        if not self._is_running:
            logger.info("Scheduler is not running")
            return True
            
        logger.info("Stopping agent scheduler...")
        if self._stop_event:
            self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
            
        self._is_running = False
        with self._stats_lock:
            logger.info("Agent scheduler stopped")
            logger.info(f"Execution stats - Total: {self._execution_count}, "
                       f"Success: {self._success_count}, Failed: {self._failure_count}")
        return True

    # Async interface
    async def astart(
        self,
        schedule_expr: str,
        max_retries: int = 3,
        run_immediately: bool = False
    ) -> bool:
        """
        Start scheduled agent execution (async).
        
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
            
        self._bind_loop(asyncio.get_running_loop())
        
        try:
            interval = ScheduleParser.parse(schedule_expr)
            self._is_running = True
            self._cancel_event.clear()
            
            logger.info(f"Starting async agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.info(f"Task: {self.task}")
            logger.info(f"Schedule: {schedule_expr} ({interval}s interval)")
            logger.info(f"Max retries: {max_retries}")
            
            # Run immediately if requested
            if run_immediately:
                logger.info("Running agent immediately before starting schedule...")
                await self._execute_with_retry_async(max_retries)
            
            # Start the async scheduling task
            self._task_handle = asyncio.create_task(
                self._run_schedule_async(interval, max_retries)
            )
            
            logger.info("Async agent scheduler started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            self._is_running = False
            return False

    async def astop(self) -> bool:
        """
        Stop the scheduler gracefully (async).
        
        Returns:
            True if stopped successfully
        """
        if not self._is_running:
            logger.info("Scheduler is not running")
            return True
            
        logger.info("Stopping async agent scheduler...")
        if self._cancel_event:
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
        with self._stats_lock:
            logger.info("Async agent scheduler stopped")
            logger.info(f"Execution stats - Total: {self._execution_count}, "
                       f"Success: {self._success_count}, Failed: {self._failure_count}")
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics (sync)."""
        with self._stats_lock:
            return {
                "is_running": self._is_running,
                "total_executions": self._execution_count,
                "successful_executions": self._success_count,
                "failed_executions": self._failure_count,
                "success_rate": (self._success_count / self._execution_count * 100) 
                               if self._execution_count > 0 else 0
            }

    async def aget_stats(self) -> Dict[str, Any]:
        """Get execution statistics (async)."""
        with self._stats_lock:
            return {
                "is_running": self._is_running,
                "execution_count": self._execution_count,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "agent_name": getattr(self.agent, 'name', 'Agent'),
                "task": self.task
            }

    def execute_once(self) -> Any:
        """Execute agent immediately (one-time execution, sync)."""
        logger.info("Executing agent once")
        try:
            result = self._executor.execute(self.task)
            logger.info(f"One-time execution successful: {result}")
            return result
        except Exception as e:
            logger.error(f"One-time execution failed: {e}")
            raise

    async def aexecute_once(self) -> Any:
        """Execute agent immediately (one-time execution, async)."""
        logger.info("Executing agent once (async)")
        try:
            result = await self._executor.aexecute(self.task)
            logger.info(f"One-time execution successful: {result}")
            return result
        except Exception as e:
            logger.error(f"One-time execution failed: {e}")
            raise

    # Internal sync methods
    def _run_schedule_sync(self, interval: int, max_retries: int):
        """Internal method to run scheduled agent executions (sync)."""
        while not self._stop_event.is_set():
            logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled agent execution")
            
            self._execute_with_retry_sync(max_retries)
            
            # Wait for next scheduled time
            logger.info(f"Next execution in {interval} seconds ({interval/3600:.1f} hours)")
            self._stop_event.wait(interval)

    def _execute_with_retry_sync(self, max_retries: int):
        """Execute agent with retry logic (sync)."""
        with self._stats_lock:
            self._execution_count += 1
        
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries}")
                result = self._executor.execute(self.task)
                
                logger.info(f"Agent execution successful on attempt {attempt + 1}")
                logger.info(f"Result: {result}")
                
                with self._stats_lock:
                    self._success_count += 1
                safe_call(self.on_success, result)
                return
                
            except Exception as e:
                last_exc = e
                logger.error(f"Agent execution failed on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    wait_time = backoff_delay(attempt)
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
        
        with self._stats_lock:
            self._failure_count += 1
        logger.error(f"Agent execution failed after {max_retries} attempts")
        safe_call(
            self.on_failure,
            last_exc if last_exc is not None
            else RuntimeError(f"Failed after {max_retries} attempts")
        )

    # Internal async methods
    async def _run_schedule_async(self, interval: int, max_retries: int) -> None:
        """Main scheduling loop with cooperative cancellation (async)."""
        try:
            while not self._cancel_event.is_set():
                try:
                    await self._execute_with_retry_async(max_retries)
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

    async def _execute_with_retry_async(self, max_retries: int) -> None:
        """Execute agent task with retry logic (async)."""
        with self._stats_lock:
            self._execution_count += 1
            
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Executing agent task (attempt {attempt + 1}/{max_retries})")
                result = await self._executor.aexecute(self.task)
                
                with self._stats_lock:
                    self._success_count += 1
                    
                safe_call(self.on_success, result)
                logger.info("Agent task executed successfully")
                return
                
            except asyncio.CancelledError:
                logger.info("Agent execution cancelled")
                raise
            except Exception as e:
                last_exc = e
                logger.error(f"Agent execution failed on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    # Wait before retry (with cancellation support)
                    try:
                        await asyncio.wait_for(
                            self._cancel_event.wait(), 
                            timeout=backoff_delay(attempt)
                        )
                        # If we get here, cancellation was requested
                        raise asyncio.CancelledError()
                    except asyncio.TimeoutError:
                        # Timeout is expected - continue to retry
                        continue
        
        # Final attempt failed
        with self._stats_lock:
            self._failure_count += 1
            
        safe_call(
            self.on_failure,
            last_exc if last_exc is not None
            else RuntimeError(f"Failed after {max_retries} attempts")
        )


# Factory function for backward compatibility
def create_agent_scheduler(
    agent,
    task: str,
    config: Optional[Dict[str, Any]] = None
) -> AgentScheduler:
    """
    Factory function to create unified agent scheduler.
    
    Args:
        agent: PraisonAI Agent instance
        task: Task description
        config: Optional configuration
        
    Returns:
        Configured AgentScheduler instance
    """
    return AgentScheduler(agent, task, config)