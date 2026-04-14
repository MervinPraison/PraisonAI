"""Task Lifecycle Protocols for PraisonAI Agents.

Provides:
- TaskStatus enum (backward-compatible with raw strings)
- TaskLifecycleManager with transition validation
- InvalidTransitionError
- EventBus integration (zero overhead when no subscribers)
"""

from enum import Enum
from typing import Optional, Callable, Dict, Set, Protocol, runtime_checkable


class TaskStatus(str, Enum):
    """Task execution status.
    
    Inherits from str so TaskStatus.NOT_STARTED == "not started" is True.
    This ensures full backward compatibility with existing raw string usage.
    """
    NOT_STARTED = "not started"
    IN_PROGRESS = "in progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value


class InvalidTransitionError(Exception):
    """Raised when an invalid task status transition is attempted."""
    def __init__(self, from_status: str, to_status: str, task_id: Optional[str] = None):
        self.from_status = from_status
        self.to_status = to_status
        self.task_id = task_id
        tid = f" (task={task_id})" if task_id else ""
        super().__init__(
            f"Invalid task transition: '{from_status}' -> '{to_status}'{tid}"
        )


# Valid transitions: from_status -> set of allowed to_statuses
_VALID_TRANSITIONS: Dict[str, Set[str]] = {
    TaskStatus.NOT_STARTED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.FAILED: {TaskStatus.IN_PROGRESS},  # retry
    TaskStatus.COMPLETED: set(),  # terminal
    TaskStatus.CANCELLED: set(),  # terminal
}


@runtime_checkable
class TaskLifecycleProtocol(Protocol):
    """Protocol for task lifecycle management."""

    def can_transition(self, from_status: str, to_status: str) -> bool: ...
    def transition(self, from_status: str, to_status: str, task_id: Optional[str] = None) -> str: ...


class TaskLifecycleManager:
    """Default task lifecycle manager with transition validation.
    
    Validates state transitions and optionally fires a callback.
    Zero overhead when no callback is configured.
    
    Usage:
        mgr = TaskLifecycleManager()
        if mgr.can_transition("not started", "in progress"):
            new = mgr.transition("not started", "in progress", task_id="t1")
    """

    def __init__(
        self,
        on_transition: Optional[Callable[[str, str, Optional[str]], None]] = None,
    ):
        self._on_transition = on_transition

    def can_transition(self, from_status: str, to_status: str) -> bool:
        """Check if a transition is valid."""
        allowed = _VALID_TRANSITIONS.get(from_status, set())
        return to_status in allowed

    def transition(
        self,
        from_status: str,
        to_status: str,
        task_id: Optional[str] = None,
    ) -> str:
        """Execute a validated transition.
        
        Args:
            from_status: Current status
            to_status: Target status
            task_id: Optional task identifier for logging/events
            
        Returns:
            The new status string
            
        Raises:
            InvalidTransitionError: If the transition is not valid
        """
        if not self.can_transition(from_status, to_status):
            raise InvalidTransitionError(from_status, to_status, task_id)
        if self._on_transition is not None:
            self._on_transition(from_status, to_status, task_id)
        return to_status
