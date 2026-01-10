"""
Subagent Delegator for PraisonAI Agents.

Provides delegation primitives for spawning subagents with scoped permissions
and context. Inspired by Gemini CLI's delegate-to-agent pattern.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from .profiles import AgentProfile, AgentMode, get_profile, BUILTIN_PROFILES

logger = logging.getLogger(__name__)


class DelegationStatus(Enum):
    """Status of a delegated task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class DelegationConfig:
    """Configuration for subagent delegation."""
    # Concurrency limits
    max_concurrent_subagents: int = 3
    max_total_subagents: int = 10
    
    # Timeouts
    default_timeout_seconds: float = 300.0
    max_timeout_seconds: float = 600.0
    
    # Resource limits
    max_steps_per_subagent: int = 50
    max_tokens_per_subagent: int = 50000
    
    # Permissions
    inherit_permissions: bool = True
    allow_nested_delegation: bool = False
    
    # Behavior
    auto_cancel_on_parent_cancel: bool = True
    collect_results: bool = True


@dataclass
class DelegationTask:
    """A task delegated to a subagent."""
    task_id: str
    agent_name: str
    objective: str
    status: DelegationStatus = DelegationStatus.PENDING
    
    # Configuration
    timeout_seconds: float = 300.0
    max_steps: int = 50
    
    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    parent_session_id: Optional[str] = None
    
    # Results
    result: Optional[str] = None
    error: Optional[str] = None
    steps_taken: int = 0
    tokens_used: int = 0
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DelegationResult:
    """Result of a delegation operation."""
    task_id: str
    agent_name: str
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    steps_taken: int = 0
    tokens_used: int = 0
    duration_seconds: float = 0.0


class SubagentDelegator:
    """
    Manages delegation of tasks to subagents.
    
    Provides:
    - Spawning subagents with scoped permissions
    - Concurrency control
    - Timeout management
    - Result collection
    - Cancellation support
    
    Example:
        delegator = SubagentDelegator()
        
        # Delegate to explorer agent
        result = await delegator.delegate(
            agent_name="explorer",
            objective="Find all authentication-related files",
            context={"workspace": "/path/to/project"}
        )
        
        # Delegate multiple tasks
        results = await delegator.delegate_parallel([
            ("explorer", "Find auth files"),
            ("explorer", "Find database models"),
        ])
    """
    
    def __init__(
        self,
        config: Optional[DelegationConfig] = None,
        agent_factory: Optional[Callable[[str], Any]] = None,
        on_task_complete: Optional[Callable[[DelegationResult], None]] = None,
    ):
        """
        Initialize the delegator.
        
        Args:
            config: Delegation configuration
            agent_factory: Factory function to create agents
            on_task_complete: Callback when task completes
        """
        self.config = config or DelegationConfig()
        self.agent_factory = agent_factory
        self.on_task_complete = on_task_complete
        
        # State
        self._tasks: Dict[str, DelegationTask] = {}
        self._running_count: int = 0
        self._total_count: int = 0
        self._task_counter: int = 0
        
        # Semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_subagents)
    
    def get_available_agents(self) -> List[str]:
        """Get list of available agent names for delegation."""
        return [
            name for name, profile in BUILTIN_PROFILES.items()
            if profile.mode in (AgentMode.SUBAGENT, AgentMode.ALL)
            and not profile.hidden
        ]
    
    def get_agent_description(self, agent_name: str) -> str:
        """Get description for an agent."""
        profile = get_profile(agent_name)
        if profile:
            return profile.description
        return f"Agent: {agent_name}"
    
    async def delegate(
        self,
        agent_name: str,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None,
        max_steps: Optional[int] = None,
    ) -> DelegationResult:
        """
        Delegate a task to a subagent.
        
        Args:
            agent_name: Name of the agent to delegate to
            objective: Task objective/description
            context: Optional context to pass to agent
            timeout_seconds: Optional timeout override
            max_steps: Optional max steps override
            
        Returns:
            DelegationResult with task outcome
        """
        # Check limits
        if self._total_count >= self.config.max_total_subagents:
            return DelegationResult(
                task_id="",
                agent_name=agent_name,
                success=False,
                error=f"Max total subagents ({self.config.max_total_subagents}) reached",
            )
        
        # Create task
        task_id = self._generate_task_id()
        task = DelegationTask(
            task_id=task_id,
            agent_name=agent_name,
            objective=objective,
            timeout_seconds=timeout_seconds or self.config.default_timeout_seconds,
            max_steps=max_steps or self.config.max_steps_per_subagent,
            context=context or {},
        )
        
        self._tasks[task_id] = task
        self._total_count += 1
        
        # Execute with concurrency control
        async with self._semaphore:
            return await self._execute_task(task)
    
    async def delegate_parallel(
        self,
        tasks: List[tuple],
        collect_all: bool = True,
    ) -> List[DelegationResult]:
        """
        Delegate multiple tasks in parallel.
        
        Args:
            tasks: List of (agent_name, objective) or (agent_name, objective, context) tuples
            collect_all: Wait for all tasks to complete
            
        Returns:
            List of DelegationResults
        """
        # Create coroutines
        coros = []
        for task_spec in tasks:
            if len(task_spec) == 2:
                agent_name, objective = task_spec
                context = None
            else:
                agent_name, objective, context = task_spec
            
            coros.append(self.delegate(agent_name, objective, context))
        
        # Execute
        if collect_all:
            results = await asyncio.gather(*coros, return_exceptions=True)
            # Convert exceptions to failed results
            processed = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    agent_name = tasks[i][0] if tasks[i] else "unknown"
                    processed.append(DelegationResult(
                        task_id="",
                        agent_name=agent_name,
                        success=False,
                        error=str(result),
                    ))
                else:
                    processed.append(result)
            return processed
        else:
            # Return as tasks complete
            return await asyncio.gather(*coros)
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a running task.
        
        Args:
            task_id: ID of task to cancel
            
        Returns:
            True if task was cancelled
        """
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        if task.status == DelegationStatus.RUNNING:
            task.status = DelegationStatus.CANCELLED
            return True
        
        return False
    
    async def cancel_all(self) -> int:
        """
        Cancel all running tasks.
        
        Returns:
            Number of tasks cancelled
        """
        cancelled = 0
        for task in self._tasks.values():
            if task.status == DelegationStatus.RUNNING:
                task.status = DelegationStatus.CANCELLED
                cancelled += 1
        return cancelled
    
    def get_task_status(self, task_id: str) -> Optional[DelegationStatus]:
        """Get status of a task."""
        task = self._tasks.get(task_id)
        return task.status if task else None
    
    def get_running_tasks(self) -> List[DelegationTask]:
        """Get all running tasks."""
        return [
            t for t in self._tasks.values()
            if t.status == DelegationStatus.RUNNING
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get delegation statistics."""
        status_counts = {}
        for task in self._tasks.values():
            status = task.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_tasks": self._total_count,
            "running_tasks": self._running_count,
            "status_counts": status_counts,
            "max_concurrent": self.config.max_concurrent_subagents,
            "max_total": self.config.max_total_subagents,
        }
    
    async def _execute_task(self, task: DelegationTask) -> DelegationResult:
        """Execute a delegation task."""
        import time
        start_time = time.time()
        
        task.status = DelegationStatus.RUNNING
        self._running_count += 1
        
        try:
            # Get agent profile
            profile = get_profile(task.agent_name)
            if not profile:
                raise ValueError(f"Unknown agent: {task.agent_name}")
            
            # Create agent
            agent = await self._create_agent(profile, task)
            
            # Execute with timeout
            try:
                result = await asyncio.wait_for(
                    self._run_agent(agent, task),
                    timeout=task.timeout_seconds,
                )
                task.result = result
                task.status = DelegationStatus.COMPLETED
                
            except asyncio.TimeoutError:
                task.status = DelegationStatus.TIMEOUT
                task.error = f"Task timed out after {task.timeout_seconds}s"
            
        except Exception as e:
            task.status = DelegationStatus.FAILED
            task.error = str(e)
            logger.exception(f"Delegation task {task.task_id} failed")
        
        finally:
            self._running_count -= 1
            duration = time.time() - start_time
        
        # Build result
        result = DelegationResult(
            task_id=task.task_id,
            agent_name=task.agent_name,
            success=task.status == DelegationStatus.COMPLETED,
            result=task.result,
            error=task.error,
            steps_taken=task.steps_taken,
            tokens_used=task.tokens_used,
            duration_seconds=duration,
        )
        
        # Callback
        if self.on_task_complete:
            try:
                self.on_task_complete(result)
            except Exception as e:
                logger.warning(f"Task complete callback error: {e}")
        
        return result
    
    async def _create_agent(self, profile: AgentProfile, task: DelegationTask) -> Any:
        """Create an agent from profile using consolidated params."""
        if self.agent_factory:
            return self.agent_factory(profile.name)
        
        # Default: create Agent from praisonaiagents
        try:
            from ..agent.agent import Agent
            
            # Filter tools based on profile
            tools = self._get_tools_for_profile(profile)
            
            # Use consolidated params (protocol-compliant)
            # output='silent' replaces verbose=False
            # execution={max_iter: N} replaces max_iter=N
            agent = Agent(
                name=profile.name,
                role=profile.name.title(),
                goal=task.objective,
                backstory=profile.system_prompt,
                tools=tools,
                output='silent',
                execution={'max_iter': min(task.max_steps, profile.max_steps)},
            )
            
            return agent
            
        except ImportError:
            raise RuntimeError("Could not import Agent class")
    
    async def _run_agent(self, agent: Any, task: DelegationTask) -> str:
        """Run an agent on a task."""
        # Build prompt with context
        prompt = task.objective
        
        if task.context:
            context_str = "\n".join(
                f"- {k}: {v}" for k, v in task.context.items()
            )
            prompt = f"Context:\n{context_str}\n\nTask: {task.objective}"
        
        # Execute
        if hasattr(agent, 'chat'):
            result = agent.chat(prompt)
        elif hasattr(agent, 'run'):
            result = agent.run(prompt)
        else:
            raise RuntimeError("Agent has no chat or run method")
        
        return str(result) if result else ""
    
    def _get_tools_for_profile(self, profile: AgentProfile) -> List[Any]:
        """Get tools for a profile, respecting restrictions."""
        # For now, return empty list - tools should be injected
        # In production, this would filter available tools
        return []
    
    def _generate_task_id(self) -> str:
        """Generate a unique task ID."""
        self._task_counter += 1
        return f"task_{self._task_counter}"


# Convenience function for quick delegation
async def delegate_to_agent(
    agent_name: str,
    objective: str,
    context: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 300.0,
) -> DelegationResult:
    """
    Quick delegation to a subagent.
    
    Args:
        agent_name: Name of agent to delegate to
        objective: Task objective
        context: Optional context
        timeout_seconds: Timeout in seconds
        
    Returns:
        DelegationResult
    """
    delegator = SubagentDelegator()
    return await delegator.delegate(
        agent_name=agent_name,
        objective=objective,
        context=context,
        timeout_seconds=timeout_seconds,
    )
