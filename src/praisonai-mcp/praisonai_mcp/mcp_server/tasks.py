"""
MCP Tasks API Implementation

Implements the Tasks API per MCP 2025-11-25 specification.
Tasks are durable state machines for tracking long-running operations.

Features:
- Task creation, update, cancellation
- Polling and deferred result retrieval
- In-memory storage (default) with optional DB adapters
- Session-scoped task management
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskStatus(str, Enum):
    """Task status values per MCP 2025-11-25 specification."""
    PENDING = "pending"  # Task created but not yet started
    WORKING = "working"  # Task is actively being processed
    INPUT_REQUIRED = "input_required"  # Task needs user input (elicitation)
    COMPLETED = "completed"  # Task finished successfully
    FAILED = "failed"  # Task failed with error
    CANCELLED = "cancelled"  # Task was cancelled


# Alias for backwards compatibility
TaskState = TaskStatus


@dataclass
class TaskProgress:
    """Task progress information."""
    current: float = 0.0
    total: Optional[float] = None
    message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"current": self.current}
        if self.total is not None:
            result["total"] = self.total
        if self.message:
            result["message"] = self.message
        return result


@dataclass
class Task:
    """
    MCP Task representation per 2025-11-25 specification.
    
    Tasks are durable state machines that carry information about the underlying
    execution state of requests, intended for requestor polling and deferred result retrieval.
    """
    id: str  # Internal ID (maps to taskId in protocol)
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    status_message: Optional[str] = None
    progress: Optional[TaskProgress] = None
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: _iso_now())
    last_updated_at: str = field(default_factory=lambda: _iso_now())
    ttl: Optional[int] = None  # TTL in milliseconds
    poll_interval: int = 5000  # Recommended poll interval in milliseconds
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Backwards compatibility alias
    @property
    def state(self) -> TaskStatus:
        return self.status
    
    @state.setter
    def state(self, value: TaskStatus) -> None:
        self.status = value
    
    @property
    def updated_at(self) -> str:
        return self.last_updated_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP task response format per 2025-11-25 spec."""
        result = {
            "taskId": self.id,
            "status": self.status.value,
            "createdAt": self.created_at,
            "lastUpdatedAt": self.last_updated_at,
        }
        
        if self.status_message:
            result["statusMessage"] = self.status_message
        
        if self.ttl is not None:
            result["ttl"] = self.ttl
        
        if self.poll_interval:
            result["pollInterval"] = self.poll_interval
        
        if self.progress:
            result["progress"] = self.progress.to_dict()
        
        if self.metadata:
            result["_meta"] = self.metadata
        
        return result
    
    def to_create_result(self) -> Dict[str, Any]:
        """Convert to CreateTaskResult format."""
        return {"task": self.to_dict()}
    
    def to_get_result(self) -> Dict[str, Any]:
        """Convert to GetTaskResult format."""
        return self.to_dict()


class TaskStore:
    """
    In-memory task storage.
    
    Can be extended with DB adapters for persistence.
    """
    
    def __init__(self, max_tasks: int = 1000, ttl: int = 3600):
        """
        Initialize task store.
        
        Args:
            max_tasks: Maximum number of tasks to store
            ttl: Task TTL in seconds (for cleanup)
        """
        self._tasks: Dict[str, Task] = {}
        self._max_tasks = max_tasks
        self._ttl = ttl
    
    def create(
        self,
        method: str,
        params: Dict[str, Any],
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Create a new task."""
        # Cleanup old tasks if at capacity
        if len(self._tasks) >= self._max_tasks:
            self._cleanup_old_tasks()
        
        task_id = f"task-{uuid.uuid4().hex[:16]}"
        task = Task(
            id=task_id,
            method=method,
            params=params,
            session_id=session_id,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        logger.debug(f"Created task: {task_id}")
        return task
    
    def get(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def update(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        status_message: Optional[str] = None,
        progress: Optional[TaskProgress] = None,
        result: Any = None,
        error: Optional[Dict[str, Any]] = None,
        state: Optional[TaskStatus] = None,  # Backwards compat alias
    ) -> Optional[Task]:
        """Update a task."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        task.last_updated_at = _iso_now()
        
        # Support both status and state (backwards compat)
        new_status = status or state
        if new_status:
            task.status = new_status
        
        if status_message:
            task.status_message = status_message
        
        if progress:
            task.progress = progress
        
        if result is not None:
            task.result = result
        
        if error:
            task.error = error
        
        logger.debug(f"Updated task {task_id}: status={task.status}")
        return task
    
    def cancel(self, task_id: str) -> Optional[Task]:
        """Cancel a task."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        if task.status in (TaskStatus.PENDING, TaskStatus.WORKING):
            task.status = TaskStatus.CANCELLED
            task.status_message = "The task was cancelled by request."
            task.last_updated_at = _iso_now()
            logger.debug(f"Cancelled task: {task_id}")
        
        return task
    
    def delete(self, task_id: str) -> bool:
        """Delete a task."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False
    
    def list_tasks(
        self,
        session_id: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        state: Optional[TaskStatus] = None,  # Backwards compat alias
        limit: int = 100,
    ) -> List[Task]:
        """List tasks with optional filtering."""
        tasks = list(self._tasks.values())
        filter_status = status or state
        
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        
        if filter_status:
            tasks = [t for t in tasks if t.status == filter_status]
        
        # Sort by created_at descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        return tasks[:limit]
    
    def _cleanup_old_tasks(self) -> None:
        """Remove old completed/failed tasks."""
        now = time.time()
        to_remove = []
        
        for task_id, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                # Parse ISO timestamp to compare
                try:
                    from datetime import datetime
                    updated = datetime.fromisoformat(task.last_updated_at.replace("Z", "+00:00"))
                    age = now - updated.timestamp()
                    if age > self._ttl:
                        to_remove.append(task_id)
                except (ValueError, AttributeError):
                    pass
        
        for task_id in to_remove:
            del self._tasks[task_id]
        
        logger.debug(f"Cleaned up {len(to_remove)} old tasks")


class TaskManager:
    """
    MCP Task Manager.
    
    Handles task lifecycle and execution.
    """
    
    def __init__(
        self,
        store: Optional[TaskStore] = None,
        executor: Optional[Callable] = None,
    ):
        """
        Initialize task manager.
        
        Args:
            store: Task storage (uses in-memory if None)
            executor: Optional async executor for task execution
        """
        self._store = store or TaskStore()
        self._executor = executor
        self._running_tasks: Dict[str, asyncio.Task] = {}
    
    async def create_task(
        self,
        method: str,
        params: Dict[str, Any],
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        execute: bool = True,
    ) -> Task:
        """
        Create and optionally start executing a task.
        
        Args:
            method: Method name for the task
            params: Task parameters
            session_id: Optional session ID
            metadata: Optional metadata
            execute: Whether to start execution immediately
            
        Returns:
            Created task
        """
        task = self._store.create(method, params, session_id, metadata)
        
        if execute and self._executor:
            # Start async execution
            asyncio_task = asyncio.create_task(
                self._execute_task(task.id)
            )
            self._running_tasks[task.id] = asyncio_task
        
        return task
    
    async def _execute_task(self, task_id: str) -> None:
        """Execute a task asynchronously."""
        task = self._store.get(task_id)
        if not task:
            return
        
        try:
            # Update to working
            self._store.update(
                task_id,
                status=TaskStatus.WORKING,
                status_message="The operation is now in progress.",
            )
            
            # Execute
            if self._executor:
                result = await self._executor(task.method, task.params)
                self._store.update(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    status_message="The operation completed successfully.",
                    result=result,
                )
            else:
                self._store.update(
                    task_id,
                    status=TaskStatus.FAILED,
                    error={"code": -32603, "message": "No executor configured"},
                )
        
        except asyncio.CancelledError:
            self._store.update(
                task_id,
                status=TaskStatus.CANCELLED,
                status_message="The task was cancelled.",
            )
        
        except Exception as e:
            logger.exception(f"Task execution failed: {task_id}")
            self._store.update(
                task_id,
                status=TaskStatus.FAILED,
                status_message=f"Task failed: {str(e)}",
                error={"code": -32603, "message": str(e)},
            )
        
        finally:
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        return self._store.get(task_id)
    
    def update_progress(
        self,
        task_id: str,
        current: float,
        total: Optional[float] = None,
        message: Optional[str] = None,
    ) -> Optional[Task]:
        """Update task progress."""
        progress = TaskProgress(current=current, total=total, message=message)
        return self._store.update(task_id, progress=progress)
    
    async def cancel_task(self, task_id: str) -> Optional[Task]:
        """Cancel a task."""
        # Cancel running asyncio task if exists
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            try:
                await self._running_tasks[task_id]
            except asyncio.CancelledError:
                pass
        
        return self._store.cancel(task_id)
    
    def list_tasks(
        self,
        session_id: Optional[str] = None,
        state: Optional[TaskState] = None,
        limit: int = 100,
    ) -> List[Task]:
        """List tasks."""
        return self._store.list_tasks(session_id, state, limit)
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        return self._store.delete(task_id)


# Global task manager instance
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """Get the global task manager."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager


def set_task_manager(manager: TaskManager) -> None:
    """Set the global task manager."""
    global _task_manager
    _task_manager = manager
