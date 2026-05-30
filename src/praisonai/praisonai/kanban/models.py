"""Task dataclasses and models for kanban system."""
import json
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List


class TaskStatus(str, Enum):
    """Task status enum matching Hermes v1."""
    TRIAGE = "triage"
    TODO = "todo"
    SCHEDULED = "scheduled"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"
    ARCHIVED = "archived"


@dataclass
class Task:
    """Task model for kanban system."""
    id: str
    title: str
    body: str = ""
    status: TaskStatus = TaskStatus.TODO
    assignee: str = ""
    priority: int = 0  # Higher number = higher priority
    tenant: str = "default"
    board: str = "default"
    workspace_kind: str = "default"
    claim_lock: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        from datetime import timezone
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc)
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/JSON serialization."""
        result = asdict(self)
        result['created_at'] = self.created_at.isoformat() if self.created_at else None
        result['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
        result['status'] = self.status.value
        result['metadata'] = json.dumps(self.metadata) if self.metadata else None
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create from dictionary."""
        # Remove fields that don't belong to Task model
        filtered_data = data.copy()
        filtered_data.pop('version', None)  # Remove version field used for optimistic locking
        
        # Handle datetime fields
        if 'created_at' in filtered_data and filtered_data['created_at']:
            filtered_data['created_at'] = datetime.fromisoformat(filtered_data['created_at'].replace('Z', '+00:00'))
        if 'updated_at' in filtered_data and filtered_data['updated_at']:
            filtered_data['updated_at'] = datetime.fromisoformat(filtered_data['updated_at'].replace('Z', '+00:00'))
        
        # Handle status enum
        if 'status' in filtered_data:
            filtered_data['status'] = TaskStatus(filtered_data['status'])
        
        # Handle metadata JSON
        if 'metadata' in filtered_data and filtered_data['metadata']:
            try:
                filtered_data['metadata'] = json.loads(filtered_data['metadata']) if isinstance(filtered_data['metadata'], str) else filtered_data['metadata']
            except (json.JSONDecodeError, TypeError):
                filtered_data['metadata'] = {}
        
        return cls(**filtered_data)


@dataclass
class TaskLink:
    """Task dependency link (DAG)."""
    parent_id: str
    child_id: str
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class TaskComment:
    """Task comment model."""
    id: str
    task_id: str
    author: str
    text: str
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'author': self.author,
            'text': self.text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


@dataclass
class TaskEvent:
    """Task audit event for SSE/WebSocket."""
    id: str
    task_id: str
    event_type: str  # created, updated, moved, deleted, commented
    data: Dict[str, Any]
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'event_type': self.event_type,
            'data': self.data,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# Protocol placeholder - will import from praisonaiagents when available
class KanbanStoreProtocol:
    """Minimal kanban store protocol - matches praisonaiagents when available."""
    
    def create_task(self, task_data: Dict[str, Any]) -> Task:
        """Create a new task."""
        ...
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        ...
    
    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Task:
        """Update task."""
        ...
    
    def delete_task(self, task_id: str) -> bool:
        """Delete task."""
        ...
    
    def list_tasks(self, filters: Optional[Dict[str, Any]] = None) -> List[Task]:
        """List tasks with optional filters."""
        ...
    
    def move_task(self, task_id: str, status: str) -> Task:
        """Move task to new status."""
        ...
    
    def get_board(self, board: str = "default") -> Dict[str, Any]:
        """Get board layout for UI."""
        ...
    
    def bulk_update(self, operations: List[Dict[str, Any]]) -> List[Task]:
        """Bulk update operations."""
        ...
    
    def add_comment(self, task_id: str, author: str, text: str) -> TaskComment:
        """Add comment to task."""
        ...
    
    def get_comments(self, task_id: str) -> List[TaskComment]:
        """Get task comments."""
        ...
    
    def add_link(self, parent_id: str, child_id: str) -> TaskLink:
        """Create task dependency."""
        ...
    
    def remove_link(self, parent_id: str, child_id: str) -> bool:
        """Remove task dependency."""
        ...
    
    def list_events(self, since: Optional[datetime] = None) -> List[TaskEvent]:
        """List events for SSE."""
        ...