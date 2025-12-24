"""
Background Runner for PraisonAI Agents.

Manages background task execution.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Callable, Union
from datetime import datetime

from .task import BackgroundTask, TaskStatus
from .config import BackgroundConfig

logger = logging.getLogger(__name__)


class BackgroundRunner:
    """
    Manages background task execution.
    
    Provides:
    - Task submission and queuing
    - Concurrent execution management
    - Progress monitoring
    - Task cancellation
    
    Example:
        runner = BackgroundRunner()
        
        # Submit a task
        task = await runner.submit(
            func=my_agent.start,
            args=("Research AI trends",),
            name="research_task"
        )
        
        # Check status
        print(task.status)
        
        # Wait for result
        result = await task.wait()
    """
    
    def __init__(self, config: Optional[BackgroundConfig] = None):
        """
        Initialize the background runner.
        
        Args:
            config: Configuration for background execution
        """
        self.config = config or BackgroundConfig()
        self._tasks: Dict[str, BackgroundTask] = {}
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_tasks)
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
    
    @property
    def tasks(self) -> List[BackgroundTask]:
        """Get all tasks."""
        return list(self._tasks.values())
    
    @property
    def running_tasks(self) -> List[BackgroundTask]:
        """Get currently running tasks."""
        return [t for t in self._tasks.values() if t.is_running]
    
    @property
    def pending_tasks(self) -> List[BackgroundTask]:
        """Get pending tasks."""
        return [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
    
    async def submit(
        self,
        func: Callable,
        args: tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
        on_complete: Optional[Callable[[BackgroundTask], None]] = None,
        on_progress: Optional[Callable[[BackgroundTask], None]] = None
    ) -> BackgroundTask:
        """
        Submit a task for background execution.
        
        Args:
            func: Function to execute (can be sync or async)
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            name: Optional task name
            timeout: Optional timeout in seconds
            on_complete: Callback when task completes
            on_progress: Callback for progress updates
            
        Returns:
            BackgroundTask object for tracking
        """
        kwargs = kwargs or {}
        
        task = BackgroundTask(
            name=name or func.__name__,
            metadata={
                "func_name": func.__name__,
                "timeout": timeout or self.config.default_timeout
            }
        )
        
        self._tasks[task.id] = task
        
        # Create the execution coroutine
        async def execute():
            async with self._semaphore:
                task.start()
                logger.info(f"Background task started: {task.name} ({task.id})")
                
                try:
                    # Check if function is async
                    if asyncio.iscoroutinefunction(func):
                        result = await asyncio.wait_for(
                            func(*args, **kwargs),
                            timeout=timeout or self.config.default_timeout
                        )
                    else:
                        # Run sync function in thread pool
                        loop = asyncio.get_event_loop()
                        result = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                            timeout=timeout or self.config.default_timeout
                        )
                    
                    task.complete(result)
                    logger.info(f"Background task completed: {task.name} ({task.id})")
                    
                    if on_complete:
                        try:
                            on_complete(task)
                        except Exception as e:
                            logger.warning(f"on_complete callback error: {e}")
                    
                    return result
                    
                except asyncio.TimeoutError:
                    task.fail(f"Task timed out after {timeout}s")
                    logger.warning(f"Background task timed out: {task.name}")
                    
                except asyncio.CancelledError:
                    task.cancel()
                    logger.info(f"Background task cancelled: {task.name}")
                    raise
                    
                except Exception as e:
                    task.fail(str(e))
                    logger.error(f"Background task failed: {task.name} - {e}")
                    
                    if on_complete:
                        try:
                            on_complete(task)
                        except Exception as cb_error:
                            logger.warning(f"on_complete callback error: {cb_error}")
        
        # Create and store the future
        task._future = asyncio.create_task(execute())
        
        return task
    
    async def submit_agent(
        self,
        agent: Any,
        prompt: str,
        name: Optional[str] = None,
        timeout: Optional[float] = None,
        on_complete: Optional[Callable[[BackgroundTask], None]] = None
    ) -> BackgroundTask:
        """
        Submit an agent task for background execution.
        
        Args:
            agent: Agent instance to run
            prompt: Prompt to send to the agent
            name: Optional task name
            timeout: Optional timeout in seconds
            on_complete: Callback when task completes
            
        Returns:
            BackgroundTask object for tracking
        """
        task_name = name or f"agent_{getattr(agent, 'name', 'unknown')}"
        
        # Determine the method to call
        if hasattr(agent, 'start'):
            func = agent.start
        elif hasattr(agent, 'chat'):
            func = agent.chat
        elif hasattr(agent, 'run'):
            func = agent.run
        else:
            raise ValueError("Agent must have start(), chat(), or run() method")
        
        return await self.submit(
            func=func,
            args=(prompt,),
            name=task_name,
            timeout=timeout,
            on_complete=on_complete
        )
    
    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.
        
        Args:
            task_id: ID of task to cancel
            
        Returns:
            True if cancelled, False if not found or already completed
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False
        
        if task.is_completed:
            return False
        
        task.cancel()
        
        if task._future and not task._future.done():
            task._future.cancel()
        
        return True
    
    async def cancel_all(self):
        """Cancel all running tasks."""
        for task in self.running_tasks:
            await self.cancel_task(task.id)
    
    async def wait_all(self, timeout: Optional[float] = None) -> List[BackgroundTask]:
        """
        Wait for all tasks to complete.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            List of completed tasks
        """
        futures = [t._future for t in self._tasks.values() if t._future]
        
        if not futures:
            return list(self._tasks.values())
        
        try:
            await asyncio.wait_for(
                asyncio.gather(*futures, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            pass
        
        return list(self._tasks.values())
    
    def clear_completed(self):
        """Remove completed tasks from tracking."""
        completed_ids = [
            task_id for task_id, task in self._tasks.items()
            if task.is_completed
        ]
        for task_id in completed_ids:
            del self._tasks[task_id]
    
    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[Dict[str, Any]]:
        """
        List tasks with optional status filter.
        
        Args:
            status: Optional status to filter by
            
        Returns:
            List of task dictionaries
        """
        tasks = self._tasks.values()
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        return [t.to_dict() for t in tasks]
    
    async def start_cleanup_loop(self):
        """Start the automatic cleanup loop."""
        if self._cleanup_task is not None:
            return
        
        async def cleanup_loop():
            while True:
                await asyncio.sleep(self.config.cleanup_delay)
                if self.config.auto_cleanup:
                    self.clear_completed()
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
    
    async def stop(self):
        """Stop the runner and cancel all tasks."""
        await self.cancel_all()
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
