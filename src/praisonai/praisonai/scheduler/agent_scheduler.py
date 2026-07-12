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
from .shared import backoff_delay
from ._base_scheduler import (
    _BaseAgentScheduler,
    _compute_run_cost,
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
        
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._executor = PraisonAgentExecutor(agent)
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._total_cost = 0.0
        self._start_time = None
        self._stats_lock = threading.Lock()
        
    def start(
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
            logger.warning("Scheduler is already running")
            return False
            
        try:
            interval = ScheduleParser.parse(schedule_expr)
            self.is_running = True
            self._stop_event.clear()
            
            logger.debug(f"Starting agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
            logger.debug(f"Task: {self.task}")
            logger.debug(f"Schedule: {schedule_expr} ({interval}s interval)")
            self.is_running = True
            self._stop_event.clear()
            self._start_time = datetime.now()
            
            # Run immediately if requested
            if run_immediately:
                logger.debug("Running agent immediately before starting schedule...")
                self._execute_with_retry(max_retries)
            
            self._thread = threading.Thread(
                target=self._run_schedule,
                args=(interval, max_retries),
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
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
            
        self.is_running = False
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
    
    def _run_schedule(self, interval: int, max_retries: int):
        """Internal method to run scheduled agent executions."""
        while not self._stop_event.is_set():
            # Check budget limit
            if self.max_cost and self._total_cost >= self.max_cost:
                logger.warning(f"Budget limit reached: ${self._total_cost:.4f} >= ${self.max_cost}")
                logger.warning("Stopping scheduler to prevent additional costs")
                self.stop()
                break
            
            logger.debug(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting scheduled agent execution")
            
            self._execute_with_retry(max_retries)
            
            # Wait for next scheduled time
            logger.debug(f"Next execution in {interval} seconds ({interval/3600:.1f} hours)")
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
                
                # Execute with timeout if specified
                if self.timeout:
                    executor = ThreadPoolExecutor(max_workers=1)
                    future = executor.submit(self._executor.execute, self.task)
                    try:
                        result = future.result(timeout=self.timeout)
                    except FuturesTimeout as e:
                        future.cancel()
                        executor.shutdown(wait=False, cancel_futures=True)
                        raise TimeoutError(f"Execution exceeded {self.timeout}s timeout") from e
                    else:
                        executor.shutdown(wait=False, cancel_futures=True)
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
                # through the shared resilient router. Best-effort — a delivery
                # failure must not fail the run or block the callback.
                self._deliver_result(result)

                if self.on_success:
                    try:
                        self.on_success(result)
                    except Exception as e:
                        logger.error(f"Callback error in on_success: {e}")
                
                # Update state file after successful execution
                self._update_state_if_daemon()
                    
                break
            
            except TimeoutError as e:
                logger.error(f"Execution timeout on attempt {attempt + 1}: {e}")
                
            except Exception as e:
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

            self._deliver_result(result)

            if self.on_success:
                try:
                    self.on_success(result)
                except Exception as e:
                    logger.error(f"Callback error in on_success: {e}")
            
            return result
        except Exception as e:
            logger.error(f"One-time execution failed: {e}")
            raise

    def _deliver_result(self, result: Any) -> None:
        """Route a successful result to the configured chat target.

        No-op when no ``deliver`` target is set. The delivery target is
        resolved and sent through the shared ``DeliveryRouter`` (rate limiting,
        idempotency dedup, dead-target self-heal), reusing the same machinery
        the gateway uses — without requiring the full gateway. Never raises: a
        delivery problem must not tear down the scheduler.
        """
        if not self.deliver:
            return
        try:
            if self._delivery is None:
                from praisonai.scheduler._delivery import SchedulerDelivery
                job_id = self.config.get("agent_id", "") if self.config else ""
                self._delivery = SchedulerDelivery(self.deliver, job_id=job_id)
            self._delivery.deliver(str(result))
        except Exception as e:
            logger.error(f"Scheduler delivery error: {e}")
    
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
        
        return self.start(interval, max_retries, run_immediately)


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
        from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue

        catalogue = BlueprintCatalogue()
        bp = catalogue.get_blueprint(blueprint_name)
        if bp is None:
            available = [b.name for b in catalogue.list_blueprints()]
            raise ValueError(
                f"Blueprint '{blueprint_name}' not found. "
                f"Available: {available}"
            )

        resolved_slots = catalogue.resolve_slots(bp, slots or {})
        prompt = catalogue.materialize_prompt(bp, resolved_slots)
        schedule_expr = catalogue.materialize_schedule(bp, resolved_slots)

        # Build a config dict recording the blueprint resolution
        config: Dict[str, Any] = {
            "blueprint": blueprint_name,
            "resolved_slots": resolved_slots,
            "deliver": deliver or bp.default_deliver,
            "agent_id": agent_id or bp.default_agent,
        }

        # Create a lightweight wrapper that makes a blueprint prompt
        # look like an agent to the scheduler (mirrors RecipeExecutorAgent).
        class BlueprintAgent:
            """Wrapper that lets a blueprint prompt drive the scheduler."""

            def __init__(self, prompt_text: str):
                self.prompt_text = prompt_text
                self.name = f"Blueprint:{blueprint_name}"

            def start(self, task: str):
                from praisonaiagents import Agent
                from praisonai._async_bridge import run_sync
                from praisonai.scheduler._dispatch import adispatch_agent
                agent = Agent(instructions=self.prompt_text)
                return run_sync(adispatch_agent(agent, self.prompt_text))

        agent = BlueprintAgent(prompt)

        timeout = timeout_override or 300
        max_cost = max_cost_override if max_cost_override is not None else 1.00

        scheduler = cls(
            agent=agent,
            task=prompt,
            config=config,
            timeout=timeout,
            max_cost=max_cost,
            on_success=on_success,
            on_failure=on_failure,
            deliver=config.get("deliver", ""),
        )

        scheduler._blueprint_name = blueprint_name
        scheduler._blueprint_slots = resolved_slots
        scheduler._yaml_schedule_config = {
            'interval': interval_override or schedule_expr,
            'max_retries': max_retries_override if max_retries_override is not None else 3,
            'run_immediately': False,
            'timeout': timeout,
            'max_cost': max_cost,
        }

        return scheduler


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
