"""
Recipe Operations Module.

Provides high-level APIs for running recipes in different operational modes:
- run_background(): Execute recipe as a background task
- submit_job(): Submit recipe to async jobs server
- schedule(): Create a scheduled recipe executor

All functions are lazy-loaded and have zero performance impact when not used.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Safe defaults
DEFAULT_TIMEOUT_SEC = 300
DEFAULT_MAX_COST_USD = 1.00
DEFAULT_MAX_RETRIES = 3


@dataclass
class BackgroundTaskHandle:
    """Handle for a background recipe task."""
    task_id: str
    recipe_name: str
    session_id: Optional[str] = None
    _runner: Any = field(default=None, repr=False)
    _task: Any = field(default=None, repr=False)
    
    async def status(self) -> str:
        """Get task status."""
        if self._runner and self._task:
            return self._task.status.value
        return "unknown"
    
    async def wait(self, timeout: Optional[float] = None) -> Any:
        """Wait for task completion and return result."""
        if self._runner and self._task:
            return await self._runner.wait_for_task(self._task.id, timeout=timeout)
        return None
    
    async def cancel(self) -> bool:
        """Cancel the task."""
        if self._runner:
            return await self._runner.cancel(self.task_id)
        return False


@dataclass
class JobHandle:
    """Handle for an async job."""
    job_id: str
    recipe_name: str
    status: str = "queued"
    poll_url: Optional[str] = None
    stream_url: Optional[str] = None
    api_url: str = "http://127.0.0.1:8005"
    
    def get_status(self) -> Dict[str, Any]:
        """Get job status from API."""
        try:
            import httpx
            with httpx.Client(timeout=30.0) as client:
                response = client.get(f"{self.api_url}/api/v1/runs/{self.job_id}")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get job status: {e}")
            return {"job_id": self.job_id, "status": "unknown", "error": str(e)}
    
    def get_result(self) -> Any:
        """Get job result from API."""
        try:
            import httpx
            with httpx.Client(timeout=30.0) as client:
                response = client.get(f"{self.api_url}/api/v1/runs/{self.job_id}/result")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get job result: {e}")
            return {"job_id": self.job_id, "error": str(e)}
    
    def cancel(self) -> bool:
        """Cancel the job."""
        try:
            import httpx
            with httpx.Client(timeout=30.0) as client:
                response = client.post(f"{self.api_url}/api/v1/runs/{self.job_id}/cancel")
                return response.status_code < 400
        except Exception as e:
            logger.error(f"Failed to cancel job: {e}")
            return False
    
    def wait(self, poll_interval: int = 5, timeout: Optional[int] = None) -> Dict[str, Any]:
        """Wait for job completion by polling."""
        import time
        start_time = time.time()
        
        while True:
            status = self.get_status()
            if status.get("status") in ("succeeded", "failed", "cancelled"):
                return self.get_result()
            
            if timeout and (time.time() - start_time) > timeout:
                return {"job_id": self.job_id, "status": "timeout", "error": "Wait timeout exceeded"}
            
            time.sleep(poll_interval)


@dataclass
class RecipeScheduler:
    """Wrapper around AgentScheduler for recipe-based scheduling."""
    recipe_name: str
    interval: str = "hourly"
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    max_cost_usd: float = DEFAULT_MAX_COST_USD
    run_immediately: bool = False
    _scheduler: Any = field(default=None, repr=False)
    _resolved: Any = field(default=None, repr=False)
    
    def start(self) -> bool:
        """Start the scheduler."""
        if self._scheduler:
            return self._scheduler.start(
                schedule_expr=self.interval,
                max_retries=self.max_retries,
                run_immediately=self.run_immediately
            )
        return False
    
    def stop(self) -> bool:
        """Stop the scheduler."""
        if self._scheduler:
            return self._scheduler.stop()
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        if self._scheduler:
            return self._scheduler.get_stats()
        return {}
    
    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        if self._scheduler:
            return self._scheduler.is_running
        return False


def run_background(
    name: str,
    *,
    input: Any = None,
    config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    timeout_sec: Optional[int] = None,
    max_concurrent: int = 5,
    on_complete: Optional[callable] = None,
) -> BackgroundTaskHandle:
    """
    Run a recipe as a background task.
    
    Args:
        name: Recipe name
        input: Input data for the recipe
        config: Configuration overrides
        session_id: Session ID for conversation continuity
        timeout_sec: Timeout in seconds (default: 300)
        max_concurrent: Max concurrent tasks (default: 5)
        on_complete: Callback when task completes
        
    Returns:
        BackgroundTaskHandle for tracking the task
        
    Example:
        task = recipe.run_background("my-recipe", input={"query": "test"})
        print(f"Task ID: {task.task_id}")
        result = await task.wait()
    """
    import asyncio
    from .bridge import resolve, execute_resolved_recipe
    
    # Resolve the recipe
    resolved = resolve(
        name,
        input_data=input,
        config=config,
        session_id=session_id,
        options={'timeout_sec': timeout_sec or DEFAULT_TIMEOUT_SEC},
    )
    
    # Import BackgroundRunner lazily
    try:
        from praisonaiagents.background import BackgroundRunner
    except ImportError:
        raise RuntimeError(
            "Background tasks require praisonaiagents. "
            "Install with: pip install praisonaiagents"
        )
    
    # Create or get runner
    runner = BackgroundRunner(max_concurrent_tasks=max_concurrent)
    
    # Define the task function
    def recipe_task():
        return execute_resolved_recipe(resolved)
    
    # Submit the task
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # We're in an async context, use create_task
        import concurrent.futures
        future = concurrent.futures.Future()
        
        async def submit_and_return():
            task = await runner.submit(
                recipe_task,
                name=f"recipe:{resolved.name}",
                timeout=timeout_sec,
                on_complete=on_complete,
            )
            return task
        
        asyncio.ensure_future(submit_and_return()).add_done_callback(
            lambda f: future.set_result(f.result())
        )
        task = future.result(timeout=10)
    else:
        # Sync context
        task = loop.run_until_complete(runner.submit(
            recipe_task,
            name=f"recipe:{resolved.name}",
            timeout=timeout_sec,
            on_complete=on_complete,
        ))
    
    return BackgroundTaskHandle(
        task_id=task.id,
        recipe_name=resolved.name,
        session_id=resolved.session_id,
        _runner=runner,
        _task=task,
    )


def submit_job(
    name: str,
    *,
    input: Any = None,
    config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    timeout_sec: Optional[int] = None,
    idempotency_key: Optional[str] = None,
    webhook_url: Optional[str] = None,
    api_url: str = "http://127.0.0.1:8005",
    wait: bool = False,
    poll_interval: int = 5,
) -> JobHandle:
    """
    Submit a recipe to the async jobs server.
    
    Args:
        name: Recipe name
        input: Input data for the recipe
        config: Configuration overrides
        session_id: Session ID for conversation continuity
        timeout_sec: Timeout in seconds (default: 3600)
        idempotency_key: Key for deduplication
        webhook_url: URL for completion webhook
        api_url: Jobs API URL (default: http://127.0.0.1:8005)
        wait: If True, wait for completion before returning
        poll_interval: Polling interval when waiting (seconds)
        
    Returns:
        JobHandle for tracking the job
        
    Example:
        job = recipe.submit_job("my-recipe", input={"query": "test"}, wait=True)
        print(f"Result: {job.get_result()}")
    """
    try:
        import httpx
    except ImportError:
        raise RuntimeError(
            "Job submission requires httpx. "
            "Install with: pip install httpx"
        )
    
    # Build request payload
    payload = {
        "prompt": str(input) if input else f"Execute recipe: {name}",
        "recipe_name": name,
        "timeout": timeout_sec or 3600,
    }
    
    if config:
        payload["config"] = config
    if session_id:
        payload["session_id"] = session_id
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    if webhook_url:
        payload["webhook_url"] = webhook_url
    
    # Submit to API
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{api_url}/api/v1/runs",
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    
    handle = JobHandle(
        job_id=data["job_id"],
        recipe_name=name,
        status=data.get("status", "queued"),
        poll_url=data.get("poll_url"),
        stream_url=data.get("stream_url"),
        api_url=api_url,
    )
    
    if wait:
        handle.wait(poll_interval=poll_interval, timeout=timeout_sec)
    
    return handle


def schedule(
    name: str,
    *,
    input: Any = None,
    config: Optional[Dict[str, Any]] = None,
    interval: Optional[str] = None,
    max_retries: Optional[int] = None,
    run_immediately: Optional[bool] = None,
    timeout_sec: Optional[int] = None,
    max_cost_usd: Optional[float] = None,
    on_success: Optional[callable] = None,
    on_failure: Optional[callable] = None,
) -> RecipeScheduler:
    """
    Create a scheduler for periodic recipe execution.
    
    Args:
        name: Recipe name
        input: Input data for the recipe
        config: Configuration overrides
        interval: Schedule interval (hourly, daily, */30m, etc.)
        max_retries: Max retry attempts (default: 3)
        run_immediately: Run once immediately (default: False)
        timeout_sec: Timeout per execution (default: 300)
        max_cost_usd: Budget limit (default: $1.00)
        on_success: Callback on successful execution
        on_failure: Callback on failed execution
        
    Returns:
        RecipeScheduler instance (call .start() to begin)
        
    Example:
        scheduler = recipe.schedule("news-monitor", interval="hourly")
        scheduler.start()
        # ... later ...
        scheduler.stop()
    """
    from .bridge import resolve, execute_resolved_recipe, get_recipe_task_description
    
    # Resolve the recipe
    resolved = resolve(
        name,
        input_data=input,
        config=config,
        options={'timeout_sec': timeout_sec or DEFAULT_TIMEOUT_SEC},
    )
    
    # Get runtime config defaults
    runtime = resolved.runtime_config
    if runtime and hasattr(runtime, 'schedule'):
        sched_config = runtime.schedule
        interval = interval or sched_config.interval
        max_retries = max_retries if max_retries is not None else sched_config.max_retries
        run_immediately = run_immediately if run_immediately is not None else sched_config.run_immediately
        timeout_sec = timeout_sec or sched_config.timeout_sec
        max_cost_usd = max_cost_usd if max_cost_usd is not None else sched_config.max_cost_usd
    
    # Apply defaults
    interval = interval or "hourly"
    max_retries = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES
    run_immediately = run_immediately if run_immediately is not None else False
    timeout_sec = timeout_sec or DEFAULT_TIMEOUT_SEC
    max_cost_usd = max_cost_usd if max_cost_usd is not None else DEFAULT_MAX_COST_USD
    
    # Import AgentScheduler lazily
    try:
        from praisonai.scheduler import AgentScheduler
    except ImportError:
        raise RuntimeError(
            "Scheduling requires praisonai scheduler module."
        )
    
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
    
    # Create the scheduler
    scheduler = AgentScheduler(
        agent=agent,
        task=task,
        timeout=timeout_sec,
        max_cost=max_cost_usd,
        on_success=on_success,
        on_failure=on_failure,
    )
    
    return RecipeScheduler(
        recipe_name=resolved.name,
        interval=interval,
        max_retries=max_retries,
        timeout_sec=timeout_sec,
        max_cost_usd=max_cost_usd,
        run_immediately=run_immediately,
        _scheduler=scheduler,
        _resolved=resolved,
    )
