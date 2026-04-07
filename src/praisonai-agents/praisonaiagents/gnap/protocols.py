"""
GNAP Protocol definitions for PraisonAI Core SDK.

Defines the interface contracts for Git-Native Agent Protocol implementations.
Following PraisonAI's protocol-first architecture pattern.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from enum import Enum


class GNAPTaskStatus(str, Enum):
    """Task status states in GNAP."""
    PENDING = "pending"
    CLAIMED = "claimed" 
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (self.COMPLETED, self.FAILED, self.CANCELLED)
        
    def is_active(self) -> bool:
        """Check if this is an active (non-terminal) state."""
        return not self.is_terminal()


@runtime_checkable
class GNAPTaskSpec(Protocol):
    """Protocol defining the structure of a GNAP task specification."""
    
    @property
    def id(self) -> str:
        """Unique task identifier."""
        ...
        
    @property 
    def status(self) -> GNAPTaskStatus:
        """Current task status."""
        ...
        
    @property
    def created_at(self) -> str:
        """ISO 8601 timestamp when task was created."""
        ...
        
    @property
    def agent_spec(self) -> Dict[str, Any]:
        """Agent configuration for this task."""
        ...
        
    @property
    def input_data(self) -> Dict[str, Any]:
        """Task input data and parameters."""
        ...
        
    @property
    def output_data(self) -> Optional[Dict[str, Any]]:
        """Task output data (None if not completed)."""
        ...
        
    @property
    def dependencies(self) -> List[str]:
        """List of task IDs this task depends on."""
        ...
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        ...
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GNAPTaskSpec:
        """Create from dictionary."""
        ...


@runtime_checkable
class GNAPRepositoryProtocol(Protocol):
    """Protocol for GNAP Git repository operations.
    
    Implementations handle the low-level Git operations for task persistence.
    This protocol abstracts away Git specifics from higher-level logic.
    """
    
    def init_repository(self, path: str, branch: str = "tasks") -> None:
        """Initialize a GNAP repository at the given path.
        
        Args:
            path: Local filesystem path for the repository
            branch: Branch name for task storage (default: "tasks")
            
        Raises:
            GNAPRepositoryError: If initialization fails
        """
        ...
        
    def clone_repository(self, url: str, path: str, branch: str = "tasks") -> None:
        """Clone a remote GNAP repository.
        
        Args:
            url: Remote repository URL
            path: Local filesystem path
            branch: Branch name for task storage
            
        Raises:
            GNAPRepositoryError: If clone fails
        """
        ...
        
    def commit_task(self, task_spec: GNAPTaskSpec) -> str:
        """Commit a task to the repository.
        
        Args:
            task_spec: Task to commit
            
        Returns:
            Git commit hash
            
        Raises:
            GNAPRepositoryError: If commit fails
        """
        ...
        
    def read_task(self, task_id: str) -> Optional[GNAPTaskSpec]:
        """Read a task from the repository.
        
        Args:
            task_id: Unique task identifier
            
        Returns:
            Task spec if found, None otherwise
        """
        ...
        
    def list_tasks(
        self, 
        status: Optional[GNAPTaskStatus] = None,
        agent_id: Optional[str] = None
    ) -> List[GNAPTaskSpec]:
        """List tasks from the repository.
        
        Args:
            status: Filter by task status
            agent_id: Filter by agent ID
            
        Returns:
            List of matching tasks
        """
        ...
        
    def sync_with_remote(self) -> None:
        """Synchronize local repository with remote.
        
        Performs git pull/push operations to stay in sync.
        
        Raises:
            GNAPRepositoryError: If sync fails
        """
        ...
        
    def get_task_history(self, task_id: str) -> List[Dict[str, Any]]:
        """Get Git history for a specific task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            List of commit records showing task evolution
        """
        ...


@runtime_checkable
class GNAPTaskProtocol(Protocol):
    """Protocol for GNAP task lifecycle management.
    
    Handles the business logic of task claiming, execution, and completion
    while using GNAPRepositoryProtocol for persistence.
    """
    
    def submit_task(
        self,
        agent_spec: Dict[str, Any],
        input_data: Dict[str, Any],
        task_id: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        priority: int = 1,
        timeout: Optional[int] = None
    ) -> str:
        """Submit a new task to the GNAP queue.
        
        Args:
            agent_spec: Agent configuration (name, instructions, model, etc.)
            input_data: Task input data and parameters
            task_id: Optional custom task ID (auto-generated if None)
            dependencies: List of task IDs this task depends on
            priority: Task priority (higher = more important)
            timeout: Task timeout in seconds
            
        Returns:
            Unique task ID
            
        Raises:
            GNAPTaskError: If submission fails
        """
        ...
        
    def claim_task(self, worker_id: str) -> Optional[GNAPTaskSpec]:
        """Claim the next available task for execution.
        
        Args:
            worker_id: Identifier of the worker claiming the task
            
        Returns:
            Task spec if one is available, None if queue is empty
            
        Raises:
            GNAPTaskError: If claiming fails
        """
        ...
        
    def update_task_progress(
        self,
        task_id: str,
        status: GNAPTaskStatus,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update task progress and status.
        
        Args:
            task_id: Task identifier
            status: New task status
            output_data: Task output data (for completed tasks)
            error_message: Error message (for failed tasks)
            
        Raises:
            GNAPTaskError: If update fails
        """
        ...
        
    def get_ready_tasks(self) -> List[GNAPTaskSpec]:
        """Get tasks that are ready for execution.
        
        Returns tasks with status PENDING whose dependencies are satisfied.
        
        Returns:
            List of ready tasks, sorted by priority
        """
        ...
        
    def cancel_task(self, task_id: str, reason: Optional[str] = None) -> None:
        """Cancel a task.
        
        Args:
            task_id: Task identifier
            reason: Optional cancellation reason
            
        Raises:
            GNAPTaskError: If cancellation fails
        """
        ...


@runtime_checkable
class GNAPProtocol(Protocol):
    """Main GNAP protocol interface.
    
    This is the primary interface that agents and applications use to interact
    with the Git-Native Agent Protocol system. It combines repository and task
    operations into a cohesive API.
    """
    
    @property
    def repository(self) -> GNAPRepositoryProtocol:
        """Access to repository operations."""
        ...
        
    @property
    def task_manager(self) -> GNAPTaskProtocol:
        """Access to task management operations."""
        ...
        
    def initialize(
        self,
        repo_path: str,
        remote_url: Optional[str] = None,
        branch: str = "tasks"
    ) -> None:
        """Initialize GNAP system.
        
        Args:
            repo_path: Local repository path
            remote_url: Optional remote repository URL
            branch: Git branch for task storage
        """
        ...
        
    def submit_agent_task(
        self,
        agent_name: str,
        instructions: str,
        prompt: str,
        model: str = "gpt-4o-mini",
        tools: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        priority: int = 1,
        session_id: Optional[str] = None
    ) -> str:
        """Submit a task for agent execution.
        
        Convenience method that formats agent configuration and submits task.
        
        Args:
            agent_name: Name of the agent
            instructions: Agent instructions/system prompt
            prompt: User prompt/task description
            model: LLM model to use
            tools: List of tool names to enable
            dependencies: Task dependencies
            priority: Task priority
            session_id: Optional session ID for context
            
        Returns:
            Task ID
        """
        ...
        
    def get_task_status(self, task_id: str) -> Optional[GNAPTaskStatus]:
        """Get the current status of a task.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task status if found, None otherwise
        """
        ...
        
    def wait_for_task(
        self,
        task_id: str,
        timeout: Optional[float] = None,
        poll_interval: float = 1.0
    ) -> Optional[Dict[str, Any]]:
        """Wait for a task to complete.
        
        Args:
            task_id: Task identifier
            timeout: Maximum time to wait in seconds
            poll_interval: How often to check status
            
        Returns:
            Task output data if completed successfully, None if failed/timeout
        """
        ...
        
    def sync(self) -> None:
        """Synchronize with remote repository."""
        ...


class GNAPError(Exception):
    """Base exception for GNAP operations."""
    pass


class GNAPRepositoryError(GNAPError):
    """Exception for repository operations."""
    pass


class GNAPTaskError(GNAPError):
    """Exception for task operations."""
    pass