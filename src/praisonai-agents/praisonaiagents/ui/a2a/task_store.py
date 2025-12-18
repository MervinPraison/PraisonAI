"""
A2A Task Store

In-memory storage for A2A Task lifecycle management.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from praisonaiagents.ui.a2a.types import (
    Task,
    TaskState,
    TaskStatus,
    Message,
    Artifact,
)


class TaskStore:
    """
    In-memory store for A2A Tasks.
    
    Manages task lifecycle including creation, status updates,
    artifact storage, and message history.
    """
    
    def __init__(self):
        """Initialize empty task store."""
        self._tasks: Dict[str, Task] = {}
    
    def create_task(self, message: Message, context_id: Optional[str] = None) -> Task:
        """
        Create a new task from an incoming message.
        
        Args:
            message: The initial message that triggers the task
            context_id: Optional context ID (uses message's context_id if not provided)
            
        Returns:
            Newly created Task in SUBMITTED state
        """
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        ctx_id = context_id or message.context_id
        
        # Create initial status
        status = TaskStatus(
            state=TaskState.SUBMITTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        # Create task with initial message in history
        task = Task(
            id=task_id,
            context_id=ctx_id,
            status=status,
            history=[message],
            artifacts=None,
        )
        
        self._tasks[task_id] = task
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Retrieve a task by its ID.
        
        Args:
            task_id: The task ID to look up
            
        Returns:
            Task if found, None otherwise
        """
        return self._tasks.get(task_id)
    
    def update_status(
        self, 
        task_id: str, 
        state: TaskState,
        message: Optional[Message] = None,
    ) -> Optional[Task]:
        """
        Update the status of a task.
        
        Args:
            task_id: The task ID to update
            state: New task state
            message: Optional status message
            
        Returns:
            Updated Task if found, None otherwise
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        # Create new status
        new_status = TaskStatus(
            state=state,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        
        # Update task (create new instance for immutability)
        updated = Task(
            id=task.id,
            context_id=task.context_id,
            status=new_status,
            artifacts=task.artifacts,
            history=task.history,
            metadata=task.metadata,
        )
        
        self._tasks[task_id] = updated
        return updated
    
    def add_artifact(self, task_id: str, artifact: Artifact) -> Optional[Task]:
        """
        Add an artifact to a task.
        
        Args:
            task_id: The task ID to update
            artifact: Artifact to add
            
        Returns:
            Updated Task if found, None otherwise
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        # Get existing artifacts or create new list
        artifacts = list(task.artifacts) if task.artifacts else []
        artifacts.append(artifact)
        
        # Update task
        updated = Task(
            id=task.id,
            context_id=task.context_id,
            status=task.status,
            artifacts=artifacts,
            history=task.history,
            metadata=task.metadata,
        )
        
        self._tasks[task_id] = updated
        return updated
    
    def add_to_history(self, task_id: str, message: Message) -> Optional[Task]:
        """
        Add a message to task history.
        
        Args:
            task_id: The task ID to update
            message: Message to add to history
            
        Returns:
            Updated Task if found, None otherwise
        """
        task = self._tasks.get(task_id)
        if not task:
            return None
        
        # Get existing history or create new list
        history = list(task.history) if task.history else []
        history.append(message)
        
        # Update task
        updated = Task(
            id=task.id,
            context_id=task.context_id,
            status=task.status,
            artifacts=task.artifacts,
            history=history,
            metadata=task.metadata,
        )
        
        self._tasks[task_id] = updated
        return updated
    
    def list_tasks(self, context_id: Optional[str] = None) -> List[Task]:
        """
        List all tasks, optionally filtered by context.
        
        Args:
            context_id: Optional context ID to filter by
            
        Returns:
            List of tasks
        """
        if context_id:
            return [t for t in self._tasks.values() if t.context_id == context_id]
        return list(self._tasks.values())
    
    def cancel_task(self, task_id: str) -> Optional[Task]:
        """
        Cancel a task.
        
        Args:
            task_id: The task ID to cancel
            
        Returns:
            Updated Task if found, None otherwise
        """
        return self.update_status(task_id, TaskState.CANCELLED)
    
    def clear(self):
        """Clear all tasks from the store."""
        self._tasks.clear()
