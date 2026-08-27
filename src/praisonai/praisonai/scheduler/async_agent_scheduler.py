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

from .shared import ScheduleParser, ScheduleTicker, backoff_delay, safe_call
from ._base_scheduler import (
    _BaseAgentScheduler,
    _compute_run_cost,
    build_from_blueprint,
    build_from_recipe,
    build_from_yaml,
)
from ._dispatch import adispatch_agent

logger = logging.getLogger(__name__)


class AsyncRecipeExecutorAgent:
    """Wrapper that makes a recipe look like an agent for the async scheduler."""

    def __init__(self, resolved_recipe):
        self.resolved = resolved_recipe
        self.name = f"AsyncRecipeAgent:{resolved_recipe.name}"

    async def astart(self, task: str) -> Any:
        from praisonai.recipe.bridge import execute_resolved_recipe
        # Run recipe execution in thread to avoid blocking async loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: execute_resolved_recipe(self.resolved)
        )

    def start(self, task: str) -> Any:
        from praisonai.recipe.bridge import execute_resolved_recipe
        # Fallback sync method
        return execute_resolved_recipe(self.resolved)


class AsyncBlueprintAgent:
    """Async twin of ``BlueprintAgent`` — dispatches without blocking the loop."""

    def __init__(self, prompt_text: str, blueprint_name: str):
        self.prompt_text = prompt_text
        self.name = f"Blueprint:{blueprint_name}"

    async def astart(self, task: str) -> Any:
        from praisonaiagents import Agent
        agent = Agent(instructions=self.prompt_text)
        return await adispatch_agent(agent, self.prompt_text)

    def start(self, task: str) -> Any:
        from praisonaiagents import Agent
        from praisonai._async_bridge import run_sync
        agent = Agent(instructions=self.prompt_text)
        return run_sync(adispatch_agent(agent, self.prompt_text))


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
            return await adispatch_agent(self.agent, task)
        except Exception as e:
            logger.error(f"Async agent execution failed: {e}")
            raise


class AsyncAgentScheduler(_BaseAgentScheduler):
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
        scheduler = AsyncAgentScheduler(
            agent, 
            task="Check news",
            timeout=30,  # 30 second timeout per execution
            max_cost=1.00  # $1.00 budget limit
        )
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
        max_cost: Optional[float] = 1.00,
        deliver: str = ""
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
            deliver: Optional delivery target token (e.g. ``"telegram:123456"``)
                routed to the resolved chat target on each successful run.
        """
        self.agent = agent
        self.task = task
        self.config = config or {}
        self.on_success = on_success
        self.on_failure = on_failure
        self.timeout = timeout
        self.max_cost = max_cost
        self.deliver = deliver or (self.config.get("deliver", "") if self.config else "")
        self._delivery = None
        # Creation-time pre-flight (Issue #3800): build the delivery wrapper now,
        # not lazily at fire time, so an unroutable token is surfaced the moment
        # the scheduler is created rather than after the first run completes.
        if self.deliver:
            self._build_delivery()
        self._total_cost = 0.0
        
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self._executor = AsyncPraisonAgentExecutor(agent)
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._undelivered_count = 0
        self._delivered_count = 0
        self._start_time: Optional[datetime] = None
        
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
        run_immediately: bool = False,
        timezone: Optional[str] = None,
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
            # Wall-clock aware ticker: cron fires at the real time-of-day (with
            # once-only catch-up across downtime); plain intervals are unchanged.
            self._load_persisted_last_run()
            ticker = ScheduleTicker(
                schedule_expr,
                last_run_at=getattr(self, "_last_run_at", None),
                timezone=timezone,
            )
            self.is_running = True
            self._start_time = datetime.now()
            self._ensure_async_primitives()  # bind to the loop start() runs on
            self._stop_event.clear()

            logger.info(f"Starting async agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.info(f"Task: {self.task}")
            if ticker.is_cron:
                logger.info(f"Schedule: {schedule_expr} (wall-clock cron)")
            else:
                logger.info(
                    f"Schedule: {schedule_expr} "
                    f"({int(ticker.seconds_until_next())}s interval)"
                )
            if self.timeout:
                logger.info(f"Timeout per execution: {self.timeout}s")
            if self.max_cost is not None:
                logger.info(f"Budget limit: ${self.max_cost}")
            
            # Run immediately if requested
            if run_immediately:
                logger.info("Running agent immediately before starting schedule...")
                await self._execute_with_retry(max_retries)
                ticker.mark_ran()
                self._last_run_at = ticker.last_run_at
                # The immediate run may have tripped the budget brake (e.g. a
                # zero budget), which sets the stop event and clears is_running.
                # In that case there is nothing left to schedule — don't spin up
                # a background task that would exit on its first tick and don't
                # report a successful start.
                if not self.is_running or (
                    self._stop_event is not None and self._stop_event.is_set()
                ):
                    logger.info(
                        "Scheduler stopped during immediate run "
                        "(budget limit); not starting background task"
                    )
                    return False

            # Start background task
            self._task = asyncio.create_task(
                self._run_schedule(ticker, max_retries)
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
        
        return self._build_stats(
            execs=execs, success=success, failed=failed, total_cost=total_cost
        )
    
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
            "total_cost_usd": round(self._total_cost, 4),
            "remaining_budget": round(self.max_cost - self._total_cost, 4) if self.max_cost is not None else None,
            # Explicit delivery-outcome counters (Issue #4454): never inferred
            # from success minus undelivered, so NOT_CONFIGURED / SUPPRESSED
            # runs never over-report a delivery.
            "delivered_deliveries": getattr(self, "_delivered_count", 0),
            "undelivered_deliveries": getattr(self, "_undelivered_count", 0),
        }
    
    async def _run_schedule(self, ticker: "ScheduleTicker", max_retries: int):
        """Internal method to run scheduled agent executions.

        For a wall-clock cron schedule this sleeps until the next real
        occurrence (running once immediately if a slot was already missed
        during downtime); for a plain interval it sleeps the fixed interval —
        preserving the previous behaviour.
        """
        try:
            self._ensure_async_primitives()
            while not self._stop_event.is_set():
                # For cron, sleep until the next wall-clock slot *before*
                # running (unless a missed slot is already due → catch up once).
                if ticker.is_cron and not ticker.is_due():
                    delay = ticker.seconds_until_next()
                    logger.info(f"Next execution in {delay:.0f} seconds (cron)")
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                        break  # Stop event was set
                    except asyncio.TimeoutError:
                        pass  # Slot reached
                    if self._stop_event.is_set():
                        break

                logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting async scheduled agent execution")

                # Advance the wall-clock anchor *before* running so the state
                # write inside _execute_with_retry persists this slot (not the
                # previous one). Otherwise a restart would restore the prior
                # anchor and replay a completed slot (see issue #3526 review).
                ticker.mark_ran()
                self._last_run_at = ticker.last_run_at

                await self._execute_with_retry(max_retries)

                if ticker.is_cron:
                    # Loop back: the top of the loop computes the next slot.
                    continue

                # Interval schedule: wait the fixed interval then run again.
                interval = ticker.seconds_until_next()
                logger.info(f"Next execution in {interval:.0f} seconds ({interval/3600:.1f} hours)")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                    break  # Stop event was set
                except asyncio.TimeoutError:
                    continue  # Timeout reached, continue with next execution
        finally:
            self.is_running = False
    
    async def _execute_with_retry(self, max_retries: int):
        """Execute agent with retry logic."""
        self._ensure_async_primitives()  # guarantees _stats_lock is bound to current loop

        # Check budget limit before incrementing execution count. Nothing
        # mutates _total_cost between here and the run, so a single guard is
        # sufficient (the previous duplicate check was redundant).
        if self._budget_exceeded():
            logger.warning(f"Budget limit reached: ${self._total_cost:.4f} >= ${self.max_cost}")
            logger.warning("Stopping scheduler to prevent additional costs")
            if self._stop_event is not None:
                self._stop_event.set()  # Actually stop the scheduler
            self.is_running = False
            return

        async with self._stats_lock:
            self._execution_count += 1

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
                
                # Compute real cost from the agent response's token usage.
                # Falls back to $0 (not a fake constant) when no usage metadata.
                run_cost, in_tok, out_tok, model = _compute_run_cost(result)
                async with self._stats_lock:
                    self._success_count += 1
                    self._total_cost += run_cost
                logger.info(
                    "Run cost: $%.4f (model=%s, in=%d, out=%d). Total: $%.4f / $%s",
                    run_cost, model or "?", in_tok, out_tok,
                    self._total_cost, self.max_cost,
                )
                
                # Deliver to the configured chat target (if any) off the event
                # loop, since the shared delivery helper uses the sync bridge,
                # and fold the outcome into truthful accounting (Issue #4454):
                # a run whose delivery fails is recorded ``undelivered`` and
                # fires ``on_failure`` instead of a silent ``on_success``.
                delivered_ok = True
                if self.deliver:
                    delivered_ok = await asyncio.to_thread(
                        self._finalize_delivery, result
                    )

                if delivered_ok:
                    safe_call(self.on_success, result)
                else:
                    logger.error(
                        "Scheduled run executed but its result could not be "
                        "delivered to the configured target"
                    )
                    safe_call(
                        self.on_failure,
                        "scheduled result could not be delivered",
                    )
                await asyncio.to_thread(self._update_state_if_daemon)
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
        await asyncio.to_thread(self._update_state_if_daemon)
    
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

            # Deliver to the configured chat target (if any) off the event loop,
            # since the shared delivery helper uses the sync bridge. Mirrors the
            # scheduled-loop success path so a one-time async run is not silently
            # undelivered.
            if self.deliver:
                await asyncio.to_thread(self._deliver_result, result)

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
            scheduler = AsyncAgentScheduler.from_yaml("agents.yaml")
            await scheduler.start("hourly")
        """
        return build_from_yaml(
            cls,
            yaml_path=yaml_path,
            interval_override=interval_override,
            max_retries_override=max_retries_override,
            timeout_override=timeout_override,
            max_cost_override=max_cost_override,
            on_success=on_success,
            on_failure=on_failure,
        )

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
        
        return await self.start(
            interval,
            max_retries,
            run_immediately,
            timezone=schedule_config.get('tz'),
        )

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
        deliver: str = "",
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
        return build_from_recipe(
            cls,
            AsyncRecipeExecutorAgent,
            recipe_name,
            input_data=input_data,
            config=config,
            interval_override=interval_override,
            max_retries_override=max_retries_override,
            timeout_override=timeout_override,
            max_cost_override=max_cost_override,
            deliver=deliver,
            on_success=on_success,
            on_failure=on_failure,
        )

    @classmethod
    def from_blueprint(
        cls,
        blueprint_name: str,
        *,
        slots: Optional[Dict[str, Any]] = None,
        deliver: str = "",
        agent_id: str = "",
        interval_override: Optional[str] = None,
        max_retries_override: Optional[int] = None,
        timeout_override: Optional[int] = None,
        max_cost_override: Optional[float] = None,
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None,
    ) -> 'AsyncAgentScheduler':
        """
        Create AsyncAgentScheduler from a blueprint template.

        Async twin of :meth:`AgentScheduler.from_blueprint`, giving the async
        surface the same blueprint parity. The blueprint prompt is dispatched
        via ``astart``, so scheduled runs never block the event loop.

        Args:
            blueprint_name: Name of the blueprint
                (``"morning-brief"``, ``"important-mail"``, ``"weekly-review"``,
                or a custom blueprint).
            slots: Parameter values to fill blueprint slots.
            deliver: Delivery target token (overrides blueprint default).
            agent_id: Agent ID to execute the job.
            interval_override: Override the resolved schedule expression.
            max_retries_override: Override max retries.
            timeout_override: Override timeout in seconds.
            max_cost_override: Override max cost in USD.
            on_success: Callback for successful execution.
            on_failure: Callback for failed execution.

        Returns:
            Configured :class:`AsyncAgentScheduler` instance.

        Raises:
            ValueError: If the blueprint is not found or required slots
                        are missing.

        Example:
            scheduler = AsyncAgentScheduler.from_blueprint(
                "morning-brief", slots={"topic": "AI"}
            )
            await scheduler.start_from_yaml_config()
        """
        return build_from_blueprint(
            cls,
            AsyncBlueprintAgent,
            blueprint_name,
            slots=slots,
            deliver=deliver,
            agent_id=agent_id,
            interval_override=interval_override,
            max_retries_override=max_retries_override,
            timeout_override=timeout_override,
            max_cost_override=max_cost_override,
            on_success=on_success,
            on_failure=on_failure,
        )


def create_async_agent_scheduler(
    agent,
    task: str,
    config: Optional[Dict[str, Any]] = None,
    on_success: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
    timeout: Optional[int] = None,
    max_cost: Optional[float] = 1.00
) -> AsyncAgentScheduler:
    """
    Factory function to create async agent scheduler.
    
    Args:
        agent: PraisonAI Agent instance
        task: Task description
        config: Optional configuration
        on_success: Callback function on successful execution
        on_failure: Callback function on failed execution
        timeout: Maximum execution time per run in seconds (None = no limit)
        max_cost: Maximum total cost in USD (default: $1.00 for safety)
        
    Returns:
        Configured AsyncAgentScheduler instance
    """
    return AsyncAgentScheduler(
        agent,
        task,
        config=config,
        on_success=on_success,
        on_failure=on_failure,
        timeout=timeout,
        max_cost=max_cost
    )
