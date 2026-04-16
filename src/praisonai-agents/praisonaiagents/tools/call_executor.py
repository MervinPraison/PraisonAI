"""
Tool Call Executor protocols for parallel and sequential tool execution.

This module implements Gap 2 from Issue #1392: enables parallel execution
of batched LLM tool calls while maintaining backward compatibility.

Design principles:
- Protocol-driven: ToolCallExecutor defines interface, concrete implementations provide behavior
- Opt-in: parallel_tool_calls=False by default (zero regression risk)
- Respects existing per-tool timeout infrastructure
- Thread-safe with bounded workers
"""

import concurrent.futures
import logging
from typing import Any, Callable, Dict, List, Optional, Protocol
from dataclasses import dataclass
from ..trace.context_events import copy_context_to_callable

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a single tool call from LLM."""
    function_name: str
    arguments: Dict[str, Any]
    tool_call_id: str
    is_ollama: bool = False


@dataclass 
class ToolResult:
    """Result of executing a single tool call."""
    function_name: str
    arguments: Dict[str, Any]
    result: Any
    tool_call_id: str
    is_ollama: bool
    error: Optional[Exception] = None


class ToolCallExecutor(Protocol):
    """Protocol for executing batched tool calls."""
    
    def execute_batch(
        self,
        tool_calls: List[ToolCall],
        execute_tool_fn: Callable[[str, Dict[str, Any], Optional[str]], Any]
    ) -> List[ToolResult]:
        """
        Execute a batch of tool calls and return results in original order.
        
        Args:
            tool_calls: List of tool calls to execute
            execute_tool_fn: Function to execute individual tools
            
        Returns:
            List of ToolResult in same order as input tool_calls
        """
        ...


class SequentialToolCallExecutor:
    """
    Sequential tool call executor - maintains current behavior.
    
    Executes tool calls one after another, preserving exact current semantics.
    """
    
    def execute_batch(
        self,
        tool_calls: List[ToolCall], 
        execute_tool_fn: Callable[[str, Dict[str, Any], Optional[str]], Any]
    ) -> List[ToolResult]:
        """Execute tool calls sequentially - current behavior."""
        results = []
        
        for tool_call in tool_calls:
            try:
                result = execute_tool_fn(
                    tool_call.function_name,
                    tool_call.arguments,
                    tool_call.tool_call_id
                )
                results.append(ToolResult(
                    function_name=tool_call.function_name,
                    arguments=tool_call.arguments,
                    result=result,
                    tool_call_id=tool_call.tool_call_id,
                    is_ollama=tool_call.is_ollama
                ))
            except Exception as e:
                logger.error(f"Tool execution error for {tool_call.function_name}: {e}")
                results.append(ToolResult(
                    function_name=tool_call.function_name,
                    arguments=tool_call.arguments,
                    result=f"Error executing tool: {e}",
                    tool_call_id=tool_call.tool_call_id,
                    is_ollama=tool_call.is_ollama,
                    error=e
                ))
        
        return results


class ParallelToolCallExecutor:
    """
    Parallel tool call executor with bounded concurrency.
    
    Executes tool calls concurrently using thread pool while respecting:
    - Per-tool timeout (from existing infrastructure) 
    - Bounded max_workers to prevent resource exhaustion
    - Result ordering (matches input order)
    """
    
    def __init__(self, max_workers: int = 5):
        """
        Initialize parallel executor.
        
        Args:
            max_workers: Maximum concurrent tool executions (default 5)
        """
        self.max_workers = max_workers
    
    def execute_batch(
        self,
        tool_calls: List[ToolCall],
        execute_tool_fn: Callable[[str, Dict[str, Any], Optional[str]], Any]
    ) -> List[ToolResult]:
        """Execute tool calls in parallel using thread pool."""
        if not tool_calls:
            return []
            
        # Single tool call - no need for parallelism overhead
        if len(tool_calls) == 1:
            sequential_executor = SequentialToolCallExecutor()
            return sequential_executor.execute_batch(tool_calls, execute_tool_fn)
        
        def _execute_single_tool(tool_call: ToolCall) -> ToolResult:
            """Execute a single tool call with error handling."""
            try:
                result = execute_tool_fn(
                    tool_call.function_name,
                    tool_call.arguments,
                    tool_call.tool_call_id
                )
                return ToolResult(
                    function_name=tool_call.function_name,
                    arguments=tool_call.arguments,
                    result=result,
                    tool_call_id=tool_call.tool_call_id,
                    is_ollama=tool_call.is_ollama
                )
            except Exception as e:
                logger.error(f"Tool execution error for {tool_call.function_name}: {e}")
                return ToolResult(
                    function_name=tool_call.function_name,
                    arguments=tool_call.arguments,
                    result=f"Error executing tool: {e}",
                    tool_call_id=tool_call.tool_call_id,
                    is_ollama=tool_call.is_ollama,
                    error=e
                )
        
        # Use ThreadPoolExecutor for sync tools
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tool calls
            future_to_index = {
                executor.submit(copy_context_to_callable(_execute_single_tool), tool_call): i
                for i, tool_call in enumerate(tool_calls)
            }
            
            # Collect results and restore original order
            results = [None] * len(tool_calls)
            for future in concurrent.futures.as_completed(future_to_index):
                index = future_to_index[future]
                results[index] = future.result()
            
            return results


def create_tool_call_executor(parallel: bool = False, max_workers: int = 5) -> ToolCallExecutor:
    """
    Factory function to create appropriate tool call executor.
    
    Args:
        parallel: If True, return ParallelToolCallExecutor; else SequentialToolCallExecutor
        max_workers: Maximum concurrent workers for parallel executor
        
    Returns:
        ToolCallExecutor implementation
    """
    if parallel:
        return ParallelToolCallExecutor(max_workers=max_workers)
    else:
        return SequentialToolCallExecutor()
