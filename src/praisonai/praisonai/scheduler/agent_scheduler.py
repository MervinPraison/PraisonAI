"""
Agent Scheduler for PraisonAI - Run agents periodically 24/7.

This module provides scheduling capabilities for running PraisonAI agents
at regular intervals, enabling 24/7 autonomous agent operations.
"""

import threading
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable

from .base import ScheduleParser, PraisonAgentExecutor

logger = logging.getLogger(__name__)


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
        on_failure: Optional[Callable] = None,
        timeout: Optional[int] = None,
        max_cost: Optional[float] = 1.00
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
        """
        self.agent = agent
        self.task = task
        self.config = config or {}
        self.on_success = on_success
        self.on_failure = on_failure
        self.timeout = timeout
        self.max_cost = max_cost
        
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread = None
        self._executor = PraisonAgentExecutor(agent)
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0
        self._total_cost = 0.0
        self._start_time = None
        
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
        runtime = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0
        return {
            "is_running": self.is_running,
            "total_executions": self._execution_count,
            "successful_executions": self._success_count,
            "failed_executions": self._failure_count,
            "success_rate": (self._success_count / self._execution_count * 100) if self._execution_count > 0 else 0,
            "total_cost_usd": round(self._total_cost, 4),
            "runtime_seconds": round(runtime, 1),
            "cost_per_execution": round(self._total_cost / self._execution_count, 4) if self._execution_count > 0 else 0
        }
    
    def _update_state_if_daemon(self):
        """Update state file with execution stats if running as daemon."""
        try:
            import os
            # Check if we're running as a daemon by looking for state file
            state_dir = os.path.expanduser("~/.praisonai/schedulers")
            if not os.path.exists(state_dir):
                return
            
            # Try to find our state file by checking all state files for matching PID
            current_pid = os.getpid()
            for state_file in os.listdir(state_dir):
                if not state_file.endswith('.json'):
                    continue
                
                state_path = os.path.join(state_dir, state_file)
                try:
                    import json
                    with open(state_path, 'r') as f:
                        state = json.load(f)
                    
                    # Check if this is our state file
                    if state.get('pid') == current_pid:
                        # Update execution stats
                        state['executions'] = self._execution_count
                        state['cost'] = round(self._total_cost, 4)
                        
                        # Write back
                        with open(state_path, 'w') as f:
                            json.dump(state, f, indent=2)
                        break
                except Exception:
                    continue
        except Exception as e:
            # Silently fail - don't break scheduler if state update fails
            logger.debug(f"Failed to update state: {e}")
    
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
        self._execution_count += 1
        success = False
        result = None
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"Attempt {attempt + 1}/{max_retries}")
                
                # Execute with timeout if specified
                if self.timeout:
                    import signal
                    
                    def timeout_handler(signum, frame):
                        raise TimeoutError(f"Execution exceeded {self.timeout}s timeout")
                    
                    # Set timeout alarm (Unix only)
                    try:
                        signal.signal(signal.SIGALRM, timeout_handler)
                        signal.alarm(self.timeout)
                        result = self._executor.execute(self.task)
                        signal.alarm(0)  # Cancel alarm
                    except AttributeError:
                        # Windows doesn't support SIGALRM, use threading.Timer fallback
                        logger.warning("Timeout not supported on this platform, executing without timeout")
                        result = self._executor.execute(self.task)
                else:
                    result = self._executor.execute(self.task)
                
                logger.debug(f"Agent execution successful on attempt {attempt + 1}")
                logger.debug(f"Result: {result}")
                
                # Always print result to stdout (even in non-verbose mode)
                print(f"\n✅ Agent Response:\n{result}\n")
                
                # Estimate cost (rough: ~$0.0001 per execution for gpt-4o-mini)
                estimated_cost = 0.0001  # Base cost estimate
                self._total_cost += estimated_cost
                logger.debug(f"Estimated cost this run: ${estimated_cost:.4f}, Total: ${self._total_cost:.4f}")
                
                self._success_count += 1
                success = True
                
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
                    wait_time = 30 * (attempt + 1)  # Exponential backoff
                    logger.debug(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
        
        if not success:
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
            
            if self.on_success:
                try:
                    self.on_success(result)
                except Exception as e:
                    logger.error(f"Callback error in on_success: {e}")
            
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
        
        # Create a recipe executor agent wrapper
        class RecipeExecutorAgent:
            """Wrapper that makes a recipe look like an agent for the scheduler."""
            def __init__(self, resolved_recipe):
                self.resolved = resolved_recipe
                self.name = f"RecipeAgent:{resolved_recipe.name}"
            
            def start(self, task: str) -> Any:
                return execute_resolved_recipe(self.resolved)
        
        # Create the agent wrapper
        agent = RecipeExecutorAgent(resolved)
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
