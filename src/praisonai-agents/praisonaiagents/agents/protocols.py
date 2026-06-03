"""Agent protocols for extensibility."""
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, runtime_checkable
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
    ) -> Awaitable[TaskResult]:
        """Execute a task with unified business logic.
        
        This method contains the single source of truth for task execution
        logic, eliminating duplication between sync/async paths.
        
        Args:
            context: All context data needed for execution
            
        Returns:
            TaskResult containing the output and execution status
        """
        ...


@dataclass
class SpawnedSubAgent:
    """Information about a spawned sub-agent.
    
    Contains metadata needed for tracking and communicating with spawned sub-agents
    in non-blocking orchestration patterns.
    """
    agent_id: str  # Unique identifier for the spawned agent
    task_id: str   # Task identifier being executed
    agent: Any     # Reference to the Agent instance
    task: Any      # Reference to the Task instance
    spawn_time: float
    parent_id: Optional[str] = None  # Parent agent/team ID
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class SubAgentCompletionEvent:
    """Event data for sub-agent completion announcements.
    
    Provides structured information when a sub-agent completes its task
    in a spawn-announce pattern.
    """
    agent_id: str
    task_id: str
    result: Any
    success: bool
    error: Optional[str] = None
    completion_time: float = None
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.completion_time is None:
            import time
            self.completion_time = time.time()
        if self.metadata is None:
            self.metadata = {}


@runtime_checkable
class SpawnAnnounceProtocol(Protocol):
    """Protocol for non-blocking spawn-and-announce multi-agent orchestration.
    
    Enables efficient parallel sub-agent workflows with push-based completion 
    notifications instead of blocking wait patterns.
    
    Key capabilities:
    - Non-blocking spawning: Spawn sub-agents and continue immediately
    - Push-based completion: Sub-agents announce completion to parent
    - Event-driven coordination: React to completion events rather than polling
    - Parallel workflow efficiency: Enable true parallel orchestration patterns
    
    Example:
        class NonBlockingTeam:
            def spawn_sub_agent(self, agent, task, callback=None):
                # Spawn agent, register completion callback
                spawned = SpawnedSubAgent(...)
                self.bus.subscribe(self._handle_completion, ["subagent.completed"])
                return spawned
                
            def _handle_completion(self, event):
                # React to completion announcement
                print(f"Sub-agent {event.data.agent_id} completed")
        
        # Check protocol compliance
        assert isinstance(NonBlockingTeam(), SpawnAnnounceProtocol)
    """
    
    def spawn_sub_agent(
        self,
        agent: Any,
        task: Any,
        completion_callback: Optional[Callable[[SubAgentCompletionEvent], Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SpawnedSubAgent:
        """Spawn a sub-agent for non-blocking execution.
        
        Launches a sub-agent to execute a task without blocking the parent.
        The sub-agent will announce completion via the event bus.
        
        Args:
            agent: Agent instance to execute the task
            task: Task instance to be executed
            completion_callback: Optional callback for completion events
            metadata: Optional metadata for the spawned agent
            
        Returns:
            SpawnedSubAgent containing spawn information
        """
        ...
    
    def announce_completion(
        self,
        agent_id: str,
        task_id: str,
        result: Any,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Announce sub-agent completion via event bus.
        
        Called by sub-agents to notify their parent of task completion.
        This enables push-based coordination instead of polling.
        
        Args:
            agent_id: Unique identifier of the completing agent
            task_id: Task identifier that was completed
            result: Task execution result
            success: Whether the task completed successfully
            error: Optional error message if task failed
            metadata: Optional additional metadata
        """
        ...
    
    def get_spawned_agents(self) -> List[SpawnedSubAgent]:
        """Get list of currently spawned sub-agents.
        
        Returns:
            List of spawned sub-agents that are still active
        """
        ...
    
    def wait_for_completions(
        self,
        timeout: Optional[float] = None,
        agent_ids: Optional[List[str]] = None
    ) -> List[SubAgentCompletionEvent]:
        """Wait for sub-agent completions (optional blocking method).
        
        Provides a way to optionally wait for completions when needed,
        while maintaining the primary non-blocking spawn-announce pattern.
        
        Args:
            timeout: Optional timeout in seconds
            agent_ids: Optional list of specific agent IDs to wait for
            
            
        Returns:
            List of completion events received within timeout
        """
        ...
