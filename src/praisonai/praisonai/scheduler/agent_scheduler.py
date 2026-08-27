"""
Agent Scheduler for PraisonAI - Run agents periodically 24/7.

This module provides scheduling capabilities for running PraisonAI agents
at regular intervals, enabling 24/7 autonomous agent operations.
"""

import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from .base import ScheduleParser, PraisonAgentExecutor
from .shared import ScheduleTicker, backoff_delay
from ._base_scheduler import (
    _BaseAgentScheduler,
    _compute_run_cost,
    build_from_blueprint,
    build_from_recipe,
    build_from_yaml,
)

logger = logging.getLogger(__name__)


class RecipeExecutorAgent:
    """Wrapper that makes a recipe look like an agent for the scheduler."""

    def __init__(self, resolved_recipe):
        self.resolved = resolved_recipe
        self.name = f"RecipeAgent:{resolved_recipe.name}"

    def start(self, task: str) -> Any:
        from praisonai.recipe.bridge import execute_resolved_recipe
        return execute_resolved_recipe(self.resolved)


class BlueprintAgent:
    """Wrapper that lets a blueprint prompt drive the sync scheduler."""

    def __init__(self, prompt_text: str, blueprint_name: str):
        self.prompt_text = prompt_text
        self.name = f"Blueprint:{blueprint_name}"

    def start(self, task: str) -> Any:
        from praisonaiagents import Agent
        from praisonai._async_bridge import run_sync
        from praisonai.scheduler._dispatch import adispatch_agent
        agent = Agent(instructions=self.prompt_text)
        return run_sync(adispatch_agent(agent, self.prompt_text))


class AgentScheduler(_BaseAgentScheduler):
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
        on_failure: Optional[Callable] = None,
        timeout: Optional[int] = None,
        max_cost: Optional[float] = 1.00,
        deliver: str = ""
    ):
        """
        Initialize agent scheduler.
        
        Args:
            agent: PraisonAI Agent instance
            task: Task description to execute
            config: Optional configuration dict
            on_success: Callback function on successful execution
            on_failure: Callback function on failed execution
            timeout: Maximum execution time per run in seconds (None = no limit)
            max_cost: Maximum total cost in USD (default: $1.00 for safety)
            deliver: Optional delivery target token (e.g. ``"telegram:123456"``).
                When set, each successful result is routed to the resolved chat
                target through the shared ``DeliveryRouter`` — same rate
                limiting, idempotency dedup and dead-target self-heal the
                gateway provides — without the full gateway.
        """
        self.agent = agent
        self.task = task
        self.config = config or {}
        self.on_success = on_success
        self.on_failure = on_failure
        self.timeout = timeout
        self.max_cost = max_cost
        # Fall back to a ``deliver`` recorded in the config dict (e.g. from
        # ``from_blueprint`` / YAML) so a target set there is honoured too.
        self.deliver = deliver or (self.config.get("deliver", "") if self.config else "")
        self._delivery = None
        # Creation-time pre-flight (Issue #3800): build the delivery wrapper now,
        # not lazily at fire time, so "where will this go?" is answered — and an
        # unroutable token warned on — the moment the scheduler is created,
        # instead of only after the first scheduled run completes.
        if self.deliver:
            self._build_delivery()
        
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._executor = PraisonAgentExecutor(agent)
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._undelivered_count = 0
        self._delivered_count = 0
        self._total_cost = 0.0
        self._start_time = None
        self._stats_lock = threading.Lock()
        # Instance-owned timeout pool with leak accounting, mirroring the
        # AgentsGenerator tool-timeout pattern. A single pool is reused across
        # retries/runs instead of allocating a fresh one per attempt; workers
        # stuck on a timed-out task are counted, and the pool is recycled once
        # half its workers have leaked so new runs aren't starved forever.
        self._timeout_executor: Optional[ThreadPoolExecutor] = None
        self._timeout_executor_lock = threading.Lock()
        self._leaked_workers = 0
        # Pool size and leak threshold are distinct: recycle once *half* the
        # workers have leaked (mirroring AgentsGenerator), not only when the
        # whole pool is dead.
        self._pool_workers = 4
        self._max_leaked_workers = max(1, self._pool_workers // 2)

    def _get_timeout_executor(self) -> ThreadPoolExecutor:
        """Lazily create/reuse this scheduler's bounded timeout pool.

        Recycles the pool once half its workers have leaked to stuck tasks so
        subsequent runs get fresh workers instead of queuing behind dead ones.
        """
        with self._timeout_executor_lock:
            if (
                self._leaked_workers >= self._max_leaked_workers
                and self._timeout_executor is not None
            ):
                self._timeout_executor.shutdown(wait=False, cancel_futures=True)
                self._timeout_executor = None
                self._leaked_workers = 0
            if self._timeout_executor is None:
                self._timeout_executor = ThreadPoolExecutor(
                    max_workers=self._pool_workers,
                    thread_name_prefix=f"praisonai-scheduler-{id(self):x}",
                )
            return self._timeout_executor

    def close(self) -> None:
        """Release the owned timeout pool; safe to call repeatedly."""
        with self._timeout_executor_lock:
            if self._timeout_executor is not None:
                self._timeout_executor.shutdown(wait=False, cancel_futures=True)
                self._timeout_executor = None
            # Reset leak accounting with the pool: the stale count belongs to the
            # discarded executor. Leaving it non-zero would make the *next* pool
            # (e.g. after a restart) get recycled on its first use — needless
            # churn against a fresh, un-leaked executor.
            self._leaked_workers = 0
        
    def start(
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
            logger.warning("Scheduler is already running")
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
            self._stop_event.clear()

            logger.debug(f"Starting agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.debug(f"Task: {self.task}")
            if ticker.is_cron:
                logger.debug(f"Schedule: {schedule_expr} (wall-clock cron)")
            else:
                logger.debug(
                    f"Schedule: {schedule_expr} "
                    f"({int(ticker.seconds_until_next())}s interval)"
                )
            self.is_running = True
            self._stop_event.clear()
            self._start_time = datetime.now()
            
            # Run immediately if requested
            if run_immediately:
                logger.debug("Running agent immediately before starting schedule...")
                self._execute_with_retry(max_retries)
                ticker.mark_ran()
                self._last_run_at = ticker.last_run_at
            
            self._thread = threading.Thread(
                target=self._run_schedule,
                args=(ticker, max_retries),
                daemon=True
            )
            self._thread.start()
            
            logger.debug("Agent scheduler started successfully")
            if self.timeout:
                logger.info(f"Timeout per execution: {self.timeout}s")
            if self.max_cost:
                logger.info(f"Budget limit: ${self.max_cost}")
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
            logger.debug("Scheduler is not running")
            return True
            
        logger.debug("Stopping agent scheduler...")
        self._stop_event.set()

        # Never join our own thread: the budget-brake path signals stop from
        # inside _run_schedule, and CPython raises "cannot join current thread".
        if (
            self._thread
            and self._thread.is_alive()
            and self._thread is not threading.current_thread()
        ):
            self._thread.join(timeout=10)

        self.is_running = False
        # Release the owned timeout pool so idle daemons don't retain workers.
        self.close()
        logger.debug("Agent scheduler stopped")
        logger.debug(f"Execution stats - Total: {self._execution_count}, Success: {self._success_count}, Failed: {self._failure_count}")
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics.
        
        Returns:
            Dictionary with execution stats including cost
        """
        with self._stats_lock:
            return self._build_stats(
                execs=self._execution_count,
                success=self._success_count,
                failed=self._failure_count,
                total_cost=self._total_cost,
            )
    
    def _run_schedule(self, ticker: "ScheduleTicker", max_retries: int):
        """Internal method to run scheduled agent executions.

        For a wall-clock cron schedule this sleeps until the next real
        occurrence (running once immediately if a slot was already missed
        during downtime); for a plain interval it sleeps the fixed interval —
        preserving the previous behaviour.
        """
        try:
            self._run_schedule_loop(ticker, max_retries)
        finally:
            # The thread is ending (budget brake, stop event, or error). Do the
            # teardown here — never call self.stop() from this thread, which
            # would self-join and raise "cannot join current thread".
            self.is_running = False
            self.close()

    def _run_schedule_loop(self, ticker: "ScheduleTicker", max_retries: int):
        while not self._stop_event.is_set():
            # Check budget limit
            if self._budget_exceeded():
                logger.warning(f"Budget limit reached: ${self._total_cost:.4f} >= ${self.max_cost}")
                logger.warning("Stopping scheduler to prevent additional costs")
                # Signal only; teardown happens in _run_schedule's finally.
                self._stop_event.set()
                break

            # For cron, sleep until the next wall-clock slot *before* running
            # (unless a missed slot is already due → catch up exactly once).
            if ticker.is_cron and not ticker.is_due():
                delay = ticker.seconds_until_next()
                logger.debug(f"Next execution in {delay:.0f} seconds (cron)")
                if self._stop_event.wait(delay):
                    break  # Stop event was set

            logger.debug(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled agent execution")

            # Advance the wall-clock anchor *before* running so the state write
            # inside _execute_with_retry persists this slot (not the previous
            # one). Otherwise a restart would restore the prior anchor and
            # replay an already-completed slot (see issue #3526 review).
            ticker.mark_ran()
            self._last_run_at = ticker.last_run_at

            self._execute_with_retry(max_retries)

            if ticker.is_cron:
                # Loop back: the top of the loop computes the next slot.
                continue

            # Interval schedule: wait the fixed interval then run again.
            interval = ticker.seconds_until_next()
            logger.debug(f"Next execution in {interval:.0f} seconds ({interval/3600:.1f} hours)")
            if self.max_cost:
                remaining = self.max_cost - self._total_cost
                logger.debug(f"Budget remaining: ${remaining:.4f}")
            self._stop_event.wait(interval)
    
    def _execute_with_retry(self, max_retries: int):
        """Execute agent with retry logic and timeout."""
        with self._stats_lock:
            self._execution_count += 1
        success = False
        result = None
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"Attempt {attempt + 1}/{max_retries}")
                
                # Execute with timeout if specified, reusing the instance-owned
                # pool. A worker stuck past the timeout cannot be cancelled once
                # running, so it is accounted as leaked and the pool recycles
                # once enough workers are stuck (see _get_timeout_executor).
                if self.timeout:
                    executor = self._get_timeout_executor()
                    future = executor.submit(self._executor.execute, self.task)
                    try:
                        result = future.result(timeout=self.timeout)
                    except FuturesTimeout as e:
                        cancelled = future.cancel()
                        if not cancelled:
                            with self._timeout_executor_lock:
                                self._leaked_workers += 1
                            logger.warning(
                                "Scheduler task exceeded %.1fs; worker may "
                                "continue running in the background.",
                                float(self.timeout),
                            )
                        raise TimeoutError(f"Execution exceeded {self.timeout}s timeout") from e
                else:
                    result = self._executor.execute(self.task)
                
                logger.debug(f"Agent execution successful on attempt {attempt + 1}")
                logger.debug(f"Result: {result}")
                
                # Always print result to stdout (even in non-verbose mode)
                print(f"\n✅ Agent Response:\n{result}\n")
                
                # Compute real cost from the agent response's token usage.
                # Falls back to $0 (not a fake constant) when no usage metadata.
                run_cost, in_tok, out_tok, model = _compute_run_cost(result)
                with self._stats_lock:
                    self._total_cost += run_cost
                    self._success_count += 1
                logger.debug(
                    "Run cost: $%.4f (model=%s, in=%d, out=%d). Total: $%.4f / $%s",
                    run_cost, model or "?", in_tok, out_tok,
                    self._total_cost, self.max_cost,
                )
                success = True

                # Deliver the result to the configured chat target (if any)
                # through the shared resilient router, and fold the delivery
                # outcome into truthful accounting (Issue #4454): a run whose
                # delivery ultimately fails is recorded ``undelivered`` and
                # fires ``on_failure`` — it is no longer a silent success.
                delivered_ok = self._finalize_delivery(result)

                if delivered_ok:
                    if self.on_success:
                        try:
                            self.on_success(result)
                        except Exception as e:
                            logger.error(f"Callback error in on_success: {e}")
                else:
                    logger.error(
                        "Scheduled run executed but its result could not be "
                        "delivered to the configured target"
                    )
                    if self.on_failure:
                        try:
                            self.on_failure(
                                "scheduled result could not be delivered"
                            )
                        except Exception as e:
                            logger.error(f"Callback error in on_failure: {e}")

                # Update state file after successful execution
                self._update_state_if_daemon()
                    
                break
            
            except Exception as e:
                # Timeouts and generic failures share the same backoff path so a
                # retry storm always honours a cooldown and stop() can preempt it.
                logger.error(f"Agent execution failed on attempt {attempt + 1}: {e}")
                
                if attempt < max_retries - 1:
                    wait_time = backoff_delay(attempt, initial=30.0, cap=300.0)
                    logger.debug(f"Waiting {wait_time}s before retry...")
                    if self._stop_event.wait(wait_time):
                        # stop() was called during backoff — exit immediately
                        return
        
        if not success:
            with self._stats_lock:
                self._failure_count += 1
            logger.error(f"Agent execution failed after {max_retries} attempts")
            
            if self.on_failure:
                try:
                    self.on_failure(f"Failed after {max_retries} attempts")
                except Exception as e:
                    logger.error(f"Callback error in on_failure: {e}")
            
            # Update state file even after failure
            self._update_state_if_daemon()
    
    def execute_once(self) -> Any:
        """
        Execute agent immediately (one-time execution).
        
        Returns:
            Agent execution result
        """
        logger.debug("Executing agent once")
        try:
            result = self._executor.execute(self.task)
            logger.debug(f"One-time execution successful: {result}")

            # Fold the delivery outcome in so a one-time run is not silently
            # undelivered either (Issue #4454).
            delivered_ok = self._finalize_delivery(result)

            if delivered_ok:
                if self.on_success:
                    try:
                        self.on_success(result)
                    except Exception as e:
                        logger.error(f"Callback error in on_success: {e}")
            else:
                logger.error(
                    "One-time run executed but its result could not be "
                    "delivered to the configured target"
                )
                if self.on_failure:
                    try:
                        self.on_failure(
                            "scheduled result could not be delivered"
                        )
                    except Exception as e:
                        logger.error(f"Callback error in on_failure: {e}")

            return result
        except Exception as e:
            logger.error(f"One-time execution failed: {e}")
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
    ) -> 'AgentScheduler':
        """
        Create AgentScheduler from agents.yaml file.
        
        Args:
            yaml_path: Path to agents.yaml file
            interval_override: Override schedule interval from YAML
            max_retries_override: Override max_retries from YAML
            on_success: Callback function on successful execution
            on_failure: Callback function on failed execution
            
        Returns:
            Configured AgentScheduler instance
            
        Example:
            scheduler = AgentScheduler.from_yaml("agents.yaml")
            scheduler.start()
            
        Example agents.yaml:
            framework: praisonai
            
            agents:
              - name: "AI News Monitor"
                role: "News Analyst"
                instructions: "Search and summarize AI news"
                tools:
                  - search_tool
            
            task: "Search for latest AI news"
            
            schedule:
              interval: "hourly"
              max_retries: 3
              run_immediately: true
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
    
    def start_from_yaml_config(self) -> bool:
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
        
        return self.start(
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
    ) -> 'AgentScheduler':
        """
        Create AgentScheduler from a recipe name.
        
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
            Configured AgentScheduler instance
            
        Example:
            scheduler = AgentScheduler.from_recipe("news-monitor")
            scheduler.start(schedule_expr="hourly")
        """
        return build_from_recipe(
            cls,
            RecipeExecutorAgent,
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
    ) -> 'AgentScheduler':
        """
        Create AgentScheduler from a blueprint template.

        Blueprints are parameterized automation templates with fillable
        slots.  This method resolves the blueprint, fills slots, materializes
        the prompt and schedule expression, and returns a configured
        :class:`AgentScheduler`.

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
            Configured :class:`AgentScheduler` instance.

        Raises:
            ValueError: If the blueprint is not found or required slots
                        are missing.

        Example::

            scheduler = AgentScheduler.from_blueprint(
                "morning-brief",
                slots={"hour": 8, "weekdays": "mon-fri"},
                deliver="telegram",
            )
            scheduler.start(schedule_expr=scheduler._yaml_schedule_config["interval"])
        """
        return build_from_blueprint(
            cls,
            BlueprintAgent,
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
