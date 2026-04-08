"""Agent protocols for extensibility."""
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, Union
from dataclasses import dataclass


@runtime_checkable
class MergeStrategyProtocol(Protocol):
    """Protocol for merging outputs from multiple agents.
    
    Used in parallel execution workflows where multiple agents
    produce outputs that need to be combined.
    
    Example:
        class CustomMerge:
            def merge(self, outputs, context=None):
                return max(outputs, key=len)  # Return longest output
        
        # Check protocol compliance
        assert isinstance(CustomMerge(), MergeStrategyProtocol)
    """
    
    def merge(
        self,
        outputs: List[Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Merge multiple agent outputs into one.
        
        Args:
            outputs: List of outputs from agents
            context: Optional context including agent names, etc.
            
        Returns:
            Merged output
        """
        ...


class FirstWinsMerge:
    """Returns the first non-None output."""
    
    def merge(
        self,
        outputs: List[Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        for output in outputs:
            if output is not None:
                return output
        return None


class ConcatMerge:
    """Concatenates all string outputs with a separator."""
    
    def __init__(self, separator: str = "\n\n"):
        self.separator = separator
    
    def merge(
        self,
        outputs: List[Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        string_outputs = [str(o) for o in outputs if o is not None]
        return self.separator.join(string_outputs)


class DictMerge:
    """Merges dictionary outputs by combining keys.
    
    Useful when agents return structured data that needs to be combined.
    Later values override earlier ones for duplicate keys.
    
    Example:
        merge = DictMerge()
        result = merge.merge([
            {"name": "Alice", "score": 10},
            {"name": "Bob", "level": 5}
        ])
        # Result: {"name": "Bob", "score": 10, "level": 5}
    """
    
    def __init__(self, deep: bool = False):
        """Initialize DictMerge.
        
        Args:
            deep: If True, recursively merge nested dicts
        """
        self.deep = deep
    
    def merge(
        self,
        outputs: List[Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for output in outputs:
            if output is None:
                continue
            if not isinstance(output, dict):
                continue
            if self.deep:
                result = self._deep_merge(result, output)
            else:
                result.update(output)
        return result
    
    def _deep_merge(self, base: Dict, update: Dict) -> Dict:
        """Recursively merge dictionaries."""
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result


@dataclass
class ExecutionContext:
    """Unified context for task execution across sync/async boundaries.
    
    Contains all data needed for task execution to eliminate duplication
    between sync and async execution paths.
    """
    task_id: int
    task: Any  # Task object
    executor_agent: Any  # Agent object
    tools: List[Any]
    task_description: str
    context_text: str
    task_prompt: str
    llm: Any  # LLM instance
    verbose: int = 0
    stream: bool = False
    user_id: Optional[str] = None


@dataclass 
class TaskResult:
    """Standardized result from task execution."""
    task_output: Any  # TaskOutput object
    success: bool
    error: Optional[str] = None


@runtime_checkable
class TaskExecutorProtocol(Protocol):
    """Protocol for unified task execution engine.
    
    Defines the interface for executing tasks in a unified way,
    eliminating duplication between async and sync execution paths.
    
    The implementation should handle all business logic including:
    - Task validation and status management
    - Memory initialization and storage
    - Agent execution with tools
    - Output processing and result creation
    
    Example:
        class MyTaskExecutor:
            def execute_task_impl(self, context: ExecutionContext) -> TaskResult:
                # Single implementation handles all execution logic
                return TaskResult(task_output=result, success=True)
                
        # Check protocol compliance
        assert isinstance(MyTaskExecutor(), TaskExecutorProtocol)
    """
    
    def execute_task_impl(
        self, 
        context: ExecutionContext
    ) -> TaskResult:
        """Execute a task with unified business logic.
        
        This method contains the single source of truth for task execution
        logic, eliminating duplication between sync/async paths.
        
        Args:
            context: All context data needed for execution
            
        Returns:
            TaskResult containing the output and execution status
        """
        ...
