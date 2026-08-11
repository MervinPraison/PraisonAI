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
    branch: Optional[str] = None
    worktree_path: Optional[str] = None
    claim_lock: Optional[str] = None
    claim_expires: Optional[datetime] = None
    worker_pid: Optional[int] = None
    last_heartbeat_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    max_retries: Optional[int] = None
    consecutive_failures: int = 0
    current_run_id: Optional[int] = None

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
        result['claim_expires'] = self.claim_expires.isoformat() if self.claim_expires else None
        result['last_heartbeat_at'] = self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None
        result['status'] = self.status.value
        result['metadata'] = json.dumps(self.metadata) if self.metadata else None
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Task':
        """Create from dictionary."""
        # Remove fields that don't belong to Task model
        filtered_data = data.copy()
        filtered_data.pop('version', None)  # Remove version field used for optimistic locking
        filtered_data.pop('idempotency_key', None)  # Stored on row but not part of model
        
        # Handle datetime fields
        if 'created_at' in filtered_data and filtered_data['created_at']:
            filtered_data['created_at'] = datetime.fromisoformat(filtered_data['created_at'].replace('Z', '+00:00'))
        if 'updated_at' in filtered_data and filtered_data['updated_at']:
            filtered_data['updated_at'] = datetime.fromisoformat(filtered_data['updated_at'].replace('Z', '+00:00'))
        if filtered_data.get('claim_expires'):
            filtered_data['claim_expires'] = datetime.fromisoformat(str(filtered_data['claim_expires']).replace('Z', '+00:00'))
        if filtered_data.get('last_heartbeat_at'):
            filtered_data['last_heartbeat_at'] = datetime.fromisoformat(str(filtered_data['last_heartbeat_at']).replace('Z', '+00:00'))
        
        # Handle status enum
        if 'status' in filtered_data:
            filtered_data['status'] = TaskStatus(filtered_data['status'])
        
        # Handle metadata JSON
        if 'metadata' in filtered_data and filtered_data['metadata']:
            try:
                filtered_data['metadata'] = json.loads(filtered_data['metadata']) if isinstance(filtered_data['metadata'], str) else filtered_data['metadata']
            except (json.JSONDecodeError, TypeError):
                filtered_data['metadata'] = {}
        
        # Normalise consecutive_failures (NULL -> 0 for legacy rows)
        if filtered_data.get('consecutive_failures') is None:
            filtered_data['consecutive_failures'] = 0
        
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


class RunOutcome(str, Enum):
    """Outcome of a single task attempt (run)."""
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CRASHED = "crashed"
    FAILED = "failed"
    GAVE_UP = "gave_up"


@dataclass
class TaskRun:
    """A single attempt (run) at executing a task.

    One row per attempt capturing the outcome, a structured summary/metadata
    handoff, and any error. ``tasks.current_run_id`` points at the active run.
    """
    id: Optional[int]
    task_id: str
    profile: str = ""
    outcome: Optional[str] = None  # one of RunOutcome values while open it is None
    summary: str = ""
    metadata: Optional[Dict[str, Any]] = None
    error: str = ""
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    def __post_init__(self):
        from datetime import timezone
        if self.started_at is None:
            self.started_at = datetime.now(timezone.utc)
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/JSON serialization."""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'profile': self.profile,
            'outcome': self.outcome,
            'summary': self.summary,
            'metadata': self.metadata,
            'error': self.error,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> 'TaskRun':
        """Create from a SQLite row dict."""
        data = dict(row)
        metadata = data.get('metadata')
        if metadata and isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        data['metadata'] = metadata or {}
        for field_name in ('started_at', 'ended_at'):
            value = data.get(field_name)
            if value and isinstance(value, str):
                data[field_name] = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return cls(**data)


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

    def claim_task(self, task_id: str, worker_id: str, *, ttl_seconds: int = 900,
                   worker_pid: Optional[int] = None) -> bool:
        """Claim a ready task with a lease."""
        ...

    def heartbeat(self, task_id: str, worker_id: str, *,
                  ttl_seconds: Optional[int] = None) -> bool:
        """Record a worker heartbeat, optionally extending the lease."""
        ...

    def reclaim_stale_claims(self, *, stale_timeout_seconds: int = 1800) -> List[str]:
        """Reclaim running tasks stranded by dead/stale workers."""
        ...


class KanbanPromotionProtocol:
    """Extension protocol for dependency-driven task promotion.

    Kept separate from the minimal KanbanStoreProtocol so base store
    implementations stay minimal; only stores that opt into auto-promotion
    need to implement this. Mirrors KanbanPromotionProtocol in
    praisonaiagents.kanban.
    """

    def recompute_ready(self) -> List[str]:
        """Promote dependent tasks to 'ready' when all parents are terminal."""
        ...