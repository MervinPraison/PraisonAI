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
            
            logger.info(f"Starting agent scheduler: {getattr(self.agent, 'name', 'Agent')}")
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
        result = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{max_retries}")
                result = self._executor.execute(self.task)
                
                logger.info(f"Agent execution successful on attempt {attempt + 1}")
                logger.info(f"Result: {result}")
                
                self._success_count += 1
                success = True
                
                if self.on_success:
                    try:
                        self.on_success(result)
                    except Exception as e:
                        logger.error(f"Callback error in on_success: {e}")
                    
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
                try:
                    self.on_failure(f"Failed after {max_retries} attempts")
                except Exception as e:
                    logger.error(f"Callback error in on_failure: {e}")
    
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
        yaml_path: str,
        interval_override: Optional[str] = None,
        max_retries_override: Optional[int] = None,
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
        
        # Create scheduler
        scheduler = cls(
            agent=agent,
            task=task,
            config=agent_config,
            on_success=on_success,
            on_failure=on_failure
        )
        
        # Store schedule config for auto-start
        scheduler._yaml_schedule_config = schedule_config
        scheduler._interval_override = interval_override
        scheduler._max_retries_override = max_retries_override
        
        return scheduler
    
    def start_from_yaml_config(self) -> bool:
        """
        Start scheduler using configuration from YAML file.
        
        Must be called after from_yaml() class method.
        
        Returns:
            True if scheduler started successfully
        """
        if not hasattr(self, '_yaml_schedule_config'):
            raise RuntimeError("start_from_yaml_config() can only be called after from_yaml()")
        
        schedule_config = self._yaml_schedule_config
        
        # Use overrides if provided, otherwise use YAML config
        interval = self._interval_override or schedule_config.get('interval', 'hourly')
        max_retries = self._max_retries_override or schedule_config.get('max_retries', 3)
        run_immediately = schedule_config.get('run_immediately', False)
        
        return self.start(
            schedule_expr=interval,
            max_retries=max_retries,
            run_immediately=run_immediately
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
