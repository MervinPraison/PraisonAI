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
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """Task execution states per MCP 2025-11-25."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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
    MCP Task representation.
    
    Tasks track durable requests with polling and deferred result retrieval.
    """
    id: str
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    state: TaskState = TaskState.PENDING
    progress: Optional[TaskProgress] = None
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP task response format."""
        result = {
            "id": self.id,
            "method": self.method,
            "state": self.state.value,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        
        if self.progress:
            result["progress"] = self.progress.to_dict()
        
        if self.state == TaskState.COMPLETED:
            result["result"] = self.result
            if self.completed_at:
                result["completedAt"] = self.completed_at
        
        if self.state == TaskState.FAILED and self.error:
            result["error"] = self.error
        
        if self.metadata:
            result["metadata"] = self.metadata
        
        return result


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
        state: Optional[TaskState] = None,
        progress: Optional[TaskProgress] = None,
        result: Any = None,
        error: Optional[Dict[str, Any]] = None,
    ) -> Optional[Task]:
        """Update a task."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        task.updated_at = time.time()
        
        if state:
            task.state = state
            if state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                task.completed_at = time.time()
        
        if progress:
            task.progress = progress
        
        if result is not None:
            task.result = result
        
        if error:
            task.error = error
        
        logger.debug(f"Updated task {task_id}: state={task.state}")
        return task
    
    def cancel(self, task_id: str) -> Optional[Task]:
        """Cancel a task."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        if task.state in (TaskState.PENDING, TaskState.RUNNING):
            task.state = TaskState.CANCELLED
            task.updated_at = time.time()
            task.completed_at = time.time()
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
        state: Optional[TaskState] = None,
        limit: int = 100,
    ) -> List[Task]:
        """List tasks with optional filtering."""
        tasks = list(self._tasks.values())
        
        if session_id:
            tasks = [t for t in tasks if t.session_id == session_id]
        
        if state:
            tasks = [t for t in tasks if t.state == state]
        
        # Sort by created_at descending
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        return tasks[:limit]
    
    def _cleanup_old_tasks(self) -> None:
        """Remove old completed/failed tasks."""
        now = time.time()
        to_remove = []
        
        for task_id, task in self._tasks.items():
            if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                if now - task.updated_at > self._ttl:
                    to_remove.append(task_id)
        
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
            # Update to running
            self._store.update(task_id, state=TaskState.RUNNING)
            
            # Execute
            if self._executor:
                result = await self._executor(task.method, task.params)
                self._store.update(
                    task_id,
                    state=TaskState.COMPLETED,
                    result=result,
                )
            else:
                self._store.update(
                    task_id,
                    state=TaskState.FAILED,
                    error={"code": -32603, "message": "No executor configured"},
                )
        
        except asyncio.CancelledError:
            self._store.update(task_id, state=TaskState.CANCELLED)
        
        except Exception as e:
            logger.exception(f"Task execution failed: {task_id}")
            self._store.update(
                task_id,
                state=TaskState.FAILED,
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
