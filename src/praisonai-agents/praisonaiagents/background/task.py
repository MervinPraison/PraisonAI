"""
Background Task for PraisonAI Agents.

Represents a task running in the background.
"""

import uuid
import asyncio
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any, Callable, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a background task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTask:
    """
    Represents a background task.
    
    Tracks the status, progress, and result of a task running
    in the background.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0.0 to 1.0
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Internal
    _future: Optional[asyncio.Future] = field(default=None, repr=False)
    _cancel_event: Optional[asyncio.Event] = field(default=None, repr=False)
    
    def __post_init__(self):
        self._cancel_event = asyncio.Event()
    
    @property
    def is_running(self) -> bool:
        """Check if task is currently running."""
        return self.status == TaskStatus.RUNNING
    
    @property
    def is_completed(self) -> bool:
        """Check if task has completed (success or failure)."""
        return self.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
    
    @property
    def is_successful(self) -> bool:
        """Check if task completed successfully."""
        return self.status == TaskStatus.COMPLETED
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Get task duration in seconds."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or datetime.now()
        return (end_time - self.started_at).total_seconds()
    
    def start(self):
        """Mark task as started."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()
    
    def complete(self, result: Any = None):
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.progress = 1.0
        self.completed_at = datetime.now()
    
    def fail(self, error: str):
        """Mark task as failed."""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
    
    def cancel(self):
        """Request task cancellation."""
        if self._cancel_event:
            self._cancel_event.set()
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()
    
    def update_progress(self, progress: float, message: Optional[str] = None):
        """Update task progress."""
        self.progress = min(max(progress, 0.0), 1.0)
        if message:
            self.metadata["last_message"] = message
    
    async def wait(self, timeout: Optional[float] = None) -> Any:
        """
        Wait for task completion.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            Task result
            
        Raises:
            asyncio.TimeoutError: If timeout exceeded
            RuntimeError: If task failed
        """
        if self._future is None:
            if self.is_completed:
                if self.status == TaskStatus.FAILED:
                    raise RuntimeError(self.error)
                return self.result
            raise RuntimeError("Task has no associated future")
        
        try:
            result = await asyncio.wait_for(self._future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            raise RuntimeError(str(e))
    
    def should_cancel(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_event is not None and self._cancel_event.is_set()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress,
            "result": str(self.result) if self.result else None,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata
        }
