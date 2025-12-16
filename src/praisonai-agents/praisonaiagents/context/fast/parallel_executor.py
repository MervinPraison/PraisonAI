"""
Parallel execution engine for Fast Context.

Provides async parallel execution of search tools with:
- Configurable parallelism (default: 8 concurrent calls)
- Timeout handling per tool call
- Result aggregation
- Error isolation (one failure doesn't affect others)
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Callable
import logging
import time

logger = logging.getLogger(__name__)


class ToolCallBatch:
    """Batch of tool calls to execute in parallel.
    
    Attributes:
        tasks: List of task dictionaries
        max_size: Maximum batch size (default: 8)
    """
    
    def __init__(self, max_size: int = 8):
        """Initialize batch.
        
        Args:
            max_size: Maximum number of tasks in batch
        """
        self.tasks: List[Dict[str, Any]] = []
        self.max_size = max_size
    
    def add(self, tool_name: str, **kwargs) -> bool:
        """Add a tool call to the batch.
        
        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments
            
        Returns:
            True if added, False if batch is full
        """
        if self.is_full:
            return False
        
        self.tasks.append({
            "tool": tool_name,
            "args": kwargs
        })
        return True
    
    @property
    def is_full(self) -> bool:
        """Check if batch is at max capacity."""
        return len(self.tasks) >= self.max_size
    
    def clear(self) -> None:
        """Clear all tasks from batch."""
        self.tasks.clear()


class ParallelExecutor:
    """Executes search tools in parallel.
    
    Uses asyncio for concurrent execution with a thread pool
    for CPU-bound operations.
    
    Attributes:
        max_parallel: Maximum concurrent executions
        timeout: Timeout per tool call in seconds
    """
    
    def __init__(
        self,
        max_parallel: int = 8,
        timeout: float = 30.0
    ):
        """Initialize executor.
        
        Args:
            max_parallel: Maximum concurrent tool calls
            timeout: Timeout per tool call in seconds
        """
        self.max_parallel = max_parallel
        self.timeout = timeout
        self._executor: Optional[ThreadPoolExecutor] = None
    
    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_parallel)
        return self._executor
    
    def _get_tool_function(self, tool_name: str) -> Optional[Callable]:
        """Get tool function by name.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool function or None if not found
        """
        # Import here to avoid circular imports
        from praisonaiagents.context.fast.search_tools import (
            grep_search,
            glob_search,
            read_file,
            list_directory
        )
        
        tools = {
            "grep_search": grep_search,
            "glob_search": glob_search,
            "read_file": read_file,
            "list_directory": list_directory
        }
        
        return tools.get(tool_name)
    
    async def _execute_single(
        self,
        task: Dict[str, Any],
        loop: asyncio.AbstractEventLoop
    ) -> Any:
        """Execute a single tool call.
        
        Args:
            task: Task dictionary with 'tool' and 'args'
            loop: Event loop for thread execution
            
        Returns:
            Tool result or error dictionary
        """
        tool_name = task.get("tool")
        args = task.get("args", {})
        
        tool_func = self._get_tool_function(tool_name)
        if tool_func is None:
            return {"error": f"Unknown tool: {tool_name}"}
        
        try:
            # Run in thread pool to avoid blocking
            executor = self._get_executor()
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, lambda: tool_func(**args)),
                timeout=self.timeout
            )
            return result
        except asyncio.TimeoutError:
            return {"error": f"Timeout executing {tool_name}", "timeout": True}
        except Exception as e:
            logger.debug(f"Error executing {tool_name}: {e}")
            return {"error": str(e)}
    
    async def execute(self, tasks: List[Dict[str, Any]]) -> List[Any]:
        """Execute multiple tool calls in parallel.
        
        Args:
            tasks: List of task dictionaries, each with 'tool' and 'args'
            
        Returns:
            List of results in same order as tasks
        """
        if not tasks:
            return []
        
        loop = asyncio.get_event_loop()
        
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_parallel)
        
        async def bounded_execute(task: Dict[str, Any]) -> Any:
            async with semaphore:
                return await self._execute_single(task, loop)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(
            *[bounded_execute(task) for task in tasks],
            return_exceptions=True
        )
        
        # Convert exceptions to error dicts
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append({"error": str(result)})
            else:
                processed_results.append(result)
        
        return processed_results
    
    def execute_sync(self, tasks: List[Dict[str, Any]]) -> List[Any]:
        """Synchronous wrapper for execute.
        
        Args:
            tasks: List of task dictionaries
            
        Returns:
            List of results
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, create new loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.execute(tasks))
                    return future.result()
            else:
                return loop.run_until_complete(self.execute(tasks))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self.execute(tasks))
    
    def close(self) -> None:
        """Close the executor and release resources."""
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class ParallelSearchCoordinator:
    """Coordinates parallel search operations across multiple turns.
    
    Implements the Fast Context search strategy:
    - Up to 8 parallel tool calls per turn
    - Maximum 4 turns
    - Aggregates results across turns
    """
    
    def __init__(
        self,
        max_parallel: int = 8,
        max_turns: int = 4,
        timeout: float = 30.0
    ):
        """Initialize coordinator.
        
        Args:
            max_parallel: Max parallel calls per turn
            max_turns: Maximum number of turns
            timeout: Timeout per tool call
        """
        self.max_parallel = max_parallel
        self.max_turns = max_turns
        self.timeout = timeout
        self.executor = ParallelExecutor(max_parallel, timeout)
        
        # Track execution stats
        self.total_tool_calls = 0
        self.turns_used = 0
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def start(self) -> None:
        """Start timing the search."""
        self.start_time = time.perf_counter()
        self.total_tool_calls = 0
        self.turns_used = 0
    
    def stop(self) -> None:
        """Stop timing the search."""
        self.end_time = time.perf_counter()
    
    @property
    def elapsed_ms(self) -> int:
        """Get elapsed time in milliseconds."""
        if self.start_time is None:
            return 0
        end = self.end_time or time.perf_counter()
        return int((end - self.start_time) * 1000)
    
    async def execute_turn(self, batch: ToolCallBatch) -> List[Any]:
        """Execute a single turn of parallel tool calls.
        
        Args:
            batch: Batch of tool calls
            
        Returns:
            List of results
        """
        if self.turns_used >= self.max_turns:
            logger.warning("Maximum turns reached")
            return []
        
        self.turns_used += 1
        self.total_tool_calls += len(batch.tasks)
        
        results = await self.executor.execute(batch.tasks)
        return results
    
    def execute_turn_sync(self, batch: ToolCallBatch) -> List[Any]:
        """Synchronous wrapper for execute_turn.
        
        Args:
            batch: Batch of tool calls
            
        Returns:
            List of results
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.execute_turn(batch))
                    return future.result()
            else:
                return loop.run_until_complete(self.execute_turn(batch))
        except RuntimeError:
            return asyncio.run(self.execute_turn(batch))
    
    def close(self) -> None:
        """Close resources."""
        self.executor.close()
