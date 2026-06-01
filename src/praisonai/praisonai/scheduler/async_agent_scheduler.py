"""Async Agent Scheduler - Canonical implementation moved from root module.

This is the canonical implementation of async agent scheduling for PraisonAI.
The old location (praisonai.async_agent_scheduler) is now a backward-compatible re-export.
"""

import asyncio
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Union
from abc import ABC, abstractmethod

from .shared import ScheduleParser, backoff_delay, safe_call

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
    - Timeout support
    - Budget tracking
    - YAML/recipe constructors
    
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
        on_failure: Optional[Callable] = None,
        timeout: Optional[int] = None,
        max_cost: Optional[float] = 1.00
    ):
        """
        Initialize async agent scheduler.
        
        Args:
            agent: PraisonAI Agent instance
            task: Task description to execute
            config: Optional configuration dict
            on_success: Callback function on successful execution
            on_failure: Callback function on failed execution
            timeout: Maximum execution time per run in seconds (None = no limit)
            max_cost: Maximum total cost in USD (default: $1.00 for safety)
        """
        self.agent = agent
        self.task = task
        self.config = config or {}
        self.on_success = on_success
        self.on_failure = on_failure
        self.timeout = timeout
        self.max_cost = max_cost
        self._total_cost = 0.0
        
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._executor = AsyncPraisonAgentExecutor(agent)
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        
        # Sync lock for async primitives creation and bound loop tracking
        self._primitives_lock = threading.Lock()
        self._stop_event: Optional[asyncio.Event] = None
        self._stats_lock: Optional[asyncio.Lock] = None
        self._bound_loop: Optional[asyncio.AbstractEventLoop] = None

    def _ensure_async_primitives(self) -> None:
        """Create async primitives if they don't exist yet.
        
        Thread-safe and loop-aware: primitives are bound to the current running loop.
        If called from a different loop, new primitives are created.
        """
        loop = asyncio.get_running_loop()  # must be called from a coroutine
        
        with self._primitives_lock:
            if self._bound_loop is not loop:
                self._stop_event = asyncio.Event()
                self._stats_lock = asyncio.Lock()
                self._bound_loop = loop

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
            self._ensure_async_primitives()  # bind to the loop start() runs on
            self._stop_event.clear()
            
            logger.info(f"Starting async agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.info(f"Task: {self.task}")
            logger.info(f"Schedule: {schedule_expr} ({interval}s interval)")
            if self.timeout:
                logger.info(f"Timeout per execution: {self.timeout}s")
            if self.max_cost:
                logger.info(f"Budget limit: ${self.max_cost}")
            
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
        
        IMPORTANT: This method must be called from the same event loop
        that was used to start the scheduler.
        
        Returns:
            True if stopped successfully
            
        Raises:
            RuntimeError: If called from a different event loop than start()
        """
        if not self.is_running:
            logger.info("Async scheduler is not running")
            return True
        
        logger.info("Stopping async agent scheduler...")
        
        # _stop_event is guaranteed non-None after a successful start()
        if self._stop_event is None:
            logger.warning("stop() called before start(); nothing to stop.")
            self.is_running = False
            return True
            
        # Ensure we're on the same loop that was bound during start()
        current_loop = asyncio.get_running_loop()
        if self._bound_loop is not None and current_loop is not self._bound_loop:
            raise RuntimeError(
                "stop() must be called from the same event loop as start(). "
                f"Expected: {self._bound_loop}, got: {current_loop}"
            )
            
        self._stop_event.set()
        
        try:
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
                    except Exception as e:
                        logger.error(f"Scheduler task raised on cancel: {e}")
                except asyncio.CancelledError:
                    # Task already cancelled; treat as expected during shutdown
                    pass
                except Exception as e:
                    logger.error(f"Scheduler task raised during stop: {e}")
        finally:
            self.is_running = False
        
        logger.info("Async agent scheduler stopped")
        
        # Log final stats with consistent snapshot
        if self._stats_lock is not None:
            async with self._stats_lock:
                total = self._execution_count
                ok = self._success_count
                fail = self._failure_count
        else:
            total = self._execution_count
            ok = self._success_count
            fail = self._failure_count
        logger.info(f"Execution stats - Total: {total}, Success: {ok}, Failed: {fail}")
        return True
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get current execution statistics (async, atomic snapshot).
        
        Returns:
            Dictionary with execution stats
        """
        return await self.get_stats_async()
    
    async def get_stats_async(self) -> Dict[str, Any]:
        """
        Get current execution statistics with atomic snapshot (async).
        
        Returns:
            Dictionary with execution stats
        """
        if self._stats_lock is None:
            # Not yet started: stats are all zero, no lock needed
            execs, success, failed, total_cost = 0, 0, 0, 0.0
        else:
            # Take atomic snapshot of all counters
            async with self._stats_lock:
                execs = self._execution_count
                success = self._success_count
                failed = self._failure_count
                total_cost = self._total_cost
        
        return {
            "is_running": self.is_running,
            "total_executions": execs,
            "successful_executions": success,
            "failed_executions": failed,
            "success_rate": (success / execs * 100) if execs > 0 else 0,
            "total_cost_usd": round(total_cost, 4),
            "remaining_budget": round(self.max_cost - total_cost, 4) if self.max_cost else None,
        }
    
    def get_stats_sync(self) -> Dict[str, Any]:
        """
        Synchronous alias for get_stats() for clarity.
        
        Returns:
            Dictionary with execution stats (best-effort)
        """
        # Always do best-effort synchronous read for simplicity
        return {
            "is_running": self.is_running,
            "total_executions": self._execution_count,
            "successful_executions": self._success_count,
            "failed_executions": self._failure_count,
            "success_rate": (self._success_count / self._execution_count * 100) if self._execution_count > 0 else 0,
        }
    
    async def _run_schedule(self, interval: int, max_retries: int):
        """Internal method to run scheduled agent executions."""
        try:
            self._ensure_async_primitives()
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
        finally:
            self.is_running = False
    
    async def _execute_with_retry(self, max_retries: int):
        """Execute agent with retry logic.
        
        TODO: Port missing features from sync version:
        - Timeout support per execution
        - Budget tracking and limits
        - Daemon state updates (_update_state_if_daemon)
        """
        self._ensure_async_primitives()  # guarantees _stats_lock is bound to current loop

        async with self._stats_lock:
            self._execution_count += 1
        
        # Check budget limit before execution
        if self.max_cost and self._total_cost >= self.max_cost:
            logger.warning(f"Budget limit reached: ${self._total_cost:.4f} >= ${self.max_cost}")
            if self._stop_event is not None:
                self._stop_event.set()
            self.is_running = False
            return
        
        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Async attempt {attempt + 1}/{max_retries}")
                
                # Execute with timeout if specified
                if self.timeout:
                    result = await asyncio.wait_for(
                        self._executor.execute(self.task), 
                        timeout=self.timeout
                    )
                else:
                    result = await self._executor.execute(self.task)
                
                logger.info(f"Async agent execution successful on attempt {attempt + 1}")
                logger.info(f"Result: {result}")
                
                # Estimate cost (rough: ~$0.0001 per execution for gpt-4o-mini)
                estimated_cost = 0.0001  # Base cost estimate
                async with self._stats_lock:
                    self._success_count += 1
                    self._total_cost += estimated_cost
                logger.info(f"Estimated cost this run: ${estimated_cost:.4f}, Total: ${self._total_cost:.4f}")
                
                safe_call(self.on_success, result)
                # TODO: Add daemon state update from sync version:
                # self._update_state_if_daemon()
                return
                
            except asyncio.TimeoutError as e:
                last_exc = e
                logger.error(f"Async execution timeout on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    wait_time = backoff_delay(attempt)
                    logger.info(f"Waiting {wait_time}s before async retry after timeout...")
                    await asyncio.sleep(wait_time)
            except Exception as e:
                last_exc = e
                logger.error(f"Async agent execution failed on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    wait_time = backoff_delay(attempt)
                    logger.info(f"Waiting {wait_time}s before async retry...")
                    await asyncio.sleep(wait_time)
        
        async with self._stats_lock:
            self._failure_count += 1
        logger.error(f"Async agent execution failed after {max_retries} attempts")
        safe_call(
            self.on_failure,
            last_exc if last_exc is not None
            else RuntimeError(f"Failed after {max_retries} attempts")
        )
        # TODO: Add daemon state update from sync version:
        # self._update_state_if_daemon()
    
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

    @classmethod
    def from_yaml(
        cls,
        yaml_path: str = "agents.yaml",
        interval_override: Optional[str] = None,
        max_retries_override: Optional[int] = None,
        timeout_override: Optional[int] = None,
        max_cost_override: Optional[float] = None,
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None
    ) -> 'AsyncAgentScheduler':
        """
        Create AsyncAgentScheduler from agents.yaml file.
        
        Args:
            yaml_path: Path to agents.yaml file
            interval_override: Override schedule interval from YAML
            max_retries_override: Override max_retries from YAML
            timeout_override: Override timeout from YAML
            max_cost_override: Override max_cost from YAML
            on_success: Callback function on successful execution
            on_failure: Callback function on failed execution
            
        Returns:
            Configured AsyncAgentScheduler instance
            
        Example:
            scheduler = await AsyncAgentScheduler.from_yaml("agents.yaml")
            await scheduler.start("hourly")
        """
        from .yaml_loader import load_agent_yaml_with_schedule, create_agent_from_config
        
        # Load configuration from YAML
        agent_config, schedule_config = load_agent_yaml_with_schedule(yaml_path)
        
        # Create agent from config
        agent = create_agent_from_config(agent_config)
        
        # Get task
        task = agent_config.get('task', '')
        if not task:
            raise ValueError("No task specified in YAML file")
        
        # Apply overrides to schedule config
        if interval_override:
            schedule_config['interval'] = interval_override
        if max_retries_override is not None:
            schedule_config['max_retries'] = max_retries_override
        if timeout_override is not None:
            schedule_config['timeout'] = timeout_override
        if max_cost_override is not None:
            schedule_config['max_cost'] = max_cost_override
        
        # Create scheduler instance with timeout and cost limits
        scheduler = cls(
            agent=agent,
            task=task,
            config=agent_config,
            timeout=schedule_config.get('timeout'),
            max_cost=schedule_config.get('max_cost'),
            on_success=on_success,
            on_failure=on_failure
        )
        
        # Store schedule config for later use
        scheduler._yaml_schedule_config = schedule_config
        
        return scheduler

    async def start_from_yaml_config(self) -> bool:
        """
        Start scheduler using configuration from YAML file.
        
        Must be called after from_yaml() class method.
        
        Returns:
            True if started successfully
        """
        if not hasattr(self, '_yaml_schedule_config'):
            raise ValueError("No YAML configuration found. Use from_yaml() first.")
        
        schedule_config = self._yaml_schedule_config
        interval = schedule_config.get('interval', 'hourly')
        max_retries = schedule_config.get('max_retries', 3)
        run_immediately = schedule_config.get('run_immediately', False)
        
        return await self.start(interval, max_retries, run_immediately)

    @classmethod
    def from_recipe(
        cls,
        recipe_name: str,
        *,
        input_data: Any = None,
        config: Optional[Dict[str, Any]] = None,
        interval_override: Optional[str] = None,
        max_retries_override: Optional[int] = None,
        timeout_override: Optional[int] = None,
        max_cost_override: Optional[float] = None,
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None
    ) -> 'AsyncAgentScheduler':
        """
        Create AsyncAgentScheduler from a recipe name.
        
        Args:
            recipe_name: Name of the recipe to schedule
            input_data: Input data for the recipe
            config: Configuration overrides for the recipe
            interval_override: Override schedule interval from recipe runtime config
            max_retries_override: Override max_retries from recipe runtime config
            timeout_override: Override timeout from recipe runtime config
            max_cost_override: Override max_cost from recipe runtime config
            on_success: Callback function on successful execution
            on_failure: Callback function on failed execution
            
        Returns:
            Configured AsyncAgentScheduler instance
            
        Example:
            scheduler = AsyncAgentScheduler.from_recipe("news-monitor")
            await scheduler.start("hourly")
        """
        from praisonai.recipe.bridge import resolve, execute_resolved_recipe, get_recipe_task_description
        
        # Resolve the recipe
        resolved = resolve(
            recipe_name,
            input_data=input_data,
            config=config or {},
            options={'timeout_sec': timeout_override or 300},
        )
        
        # Get runtime config defaults from recipe
        interval = interval_override or "hourly"
        max_retries = max_retries_override if max_retries_override is not None else 3
        timeout = timeout_override or 300
        max_cost = max_cost_override if max_cost_override is not None else 1.00
        
        runtime = resolved.runtime_config
        if runtime and hasattr(runtime, 'schedule'):
            sched_config = runtime.schedule
            interval = interval_override or sched_config.interval
            max_retries = max_retries_override if max_retries_override is not None else sched_config.max_retries
            timeout = timeout_override or sched_config.timeout_sec
            max_cost = max_cost_override if max_cost_override is not None else sched_config.max_cost_usd
        
        # Create a recipe executor agent wrapper that supports async
        class AsyncRecipeExecutorAgent:
            """Wrapper that makes a recipe look like an agent for the async scheduler."""
            def __init__(self, resolved_recipe):
                self.resolved = resolved_recipe
                self.name = f"AsyncRecipeAgent:{resolved_recipe.name}"
            
            async def astart(self, task: str) -> Any:
                # Run recipe execution in thread to avoid blocking async loop
                import asyncio
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, lambda: execute_resolved_recipe(self.resolved)
                )
            
            def start(self, task: str) -> Any:
                # Fallback sync method
                return execute_resolved_recipe(self.resolved)
        
        # Create the agent wrapper
        agent = AsyncRecipeExecutorAgent(resolved)
        task = get_recipe_task_description(resolved)
        
        # Create scheduler instance
        scheduler = cls(
            agent=agent,
            task=task,
            timeout=timeout,
            max_cost=max_cost,
            on_success=on_success,
            on_failure=on_failure,
        )
        
        # Store recipe metadata and schedule config
        scheduler._recipe_name = recipe_name
        scheduler._recipe_resolved = resolved
        scheduler._yaml_schedule_config = {
            'interval': interval,
            'max_retries': max_retries,
            'run_immediately': False,
            'timeout': timeout,
            'max_cost': max_cost,
        }
        
        return scheduler


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