"""
GNAP data models for PraisonAI Core SDK.

Lightweight dataclasses following PraisonAI's protocol-driven architecture.
No heavy dependencies - only core Python types and dataclasses.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .protocols import GNAPTaskStatus, GNAPTaskSpec


@dataclass
class TaskDependency:
    """Represents a task dependency relationship."""
    task_id: str
    dependency_id: str
    dependency_type: str = "completion"  # "completion", "output", "condition"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "dependency_id": self.dependency_id,
            "dependency_type": self.dependency_type,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskDependency":
        return cls(
            task_id=data.get("task_id", ""),
            dependency_id=data.get("dependency_id", ""),
            dependency_type=data.get("dependency_type", "completion"),
        )


@dataclass 
class GNAPTask:
    """Concrete implementation of GNAPTaskSpec protocol.
    
    Represents a task in the Git-Native Agent Protocol system.
    Stored as JSON in Git commits for durability and distribution.
    """
    
    # Core identification
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: GNAPTaskStatus = GNAPTaskStatus.PENDING
    
    # Timing
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    claimed_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Agent configuration
    agent_spec: Dict[str, Any] = field(default_factory=dict)
    
    # Task data
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Optional[Dict[str, Any]] = None
    
    # Execution context
    worker_id: Optional[str] = None
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    # Dependencies and scheduling
    dependencies: List[str] = field(default_factory=list)
    priority: int = 1
    timeout_seconds: Optional[int] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Ensure proper types after initialization."""
        if isinstance(self.status, str):
            self.status = GNAPTaskStatus(self.status)
    
    @property
    def is_ready(self) -> bool:
        """Check if task is ready for execution (dependencies satisfied)."""
        return (
            self.status == GNAPTaskStatus.PENDING and
            len(self.dependencies) == 0  # Simplified - would check actual deps
        )
    
    @property
    def is_terminal(self) -> bool:
        """Check if task is in terminal state."""
        return self.status.is_terminal()
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Get task duration in seconds."""
        if not self.started_at or not self.completed_at:
            return None
        
        try:
            start = time.mktime(time.strptime(self.started_at, "%Y-%m-%dT%H:%M:%S.%fZ"))
            end = time.mktime(time.strptime(self.completed_at, "%Y-%m-%dT%H:%M:%S.%fZ"))
            return end - start
        except (ValueError, TypeError):
            return None
    
    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return (
            self.status == GNAPTaskStatus.FAILED and
            self.retry_count < self.max_retries
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "status": self.status.value,
            "created_at": self.created_at,
            "claimed_at": self.claimed_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "agent_spec": self.agent_spec,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "worker_id": self.worker_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "timeout_seconds": self.timeout_seconds,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "tags": self.tags,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GNAPTask":
        """Create from dictionary."""
        # Handle status conversion
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = GNAPTaskStatus(status)
        
        return cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            status=status,
            created_at=data.get("created_at", time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")),
            claimed_at=data.get("claimed_at"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            agent_spec=data.get("agent_spec", {}),
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data"),
            worker_id=data.get("worker_id"),
            session_id=data.get("session_id"),
            trace_id=data.get("trace_id"),
            dependencies=data.get("dependencies", []),
            priority=data.get("priority", 1),
            timeout_seconds=data.get("timeout_seconds"),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class GNAPConfig:
    """Configuration for GNAP system."""
    
    # Repository settings
    repo_path: str = ".gnap"
    remote_url: Optional[str] = None
    branch: str = "tasks"
    
    # Worker settings
    worker_id: Optional[str] = None
    poll_interval_seconds: float = 5.0
    
    # Task settings
    default_priority: int = 1
    default_timeout_seconds: Optional[int] = None
    default_max_retries: int = 3
    
    # Sync settings
    auto_sync: bool = True
    sync_interval_seconds: float = 60.0
    
    # Performance settings
    max_concurrent_tasks: int = 4
    task_history_limit: int = 1000
    
    # Git settings
    git_author_name: str = "GNAP Agent"
    git_author_email: str = "gnap@praisonai.com"
    
    def __post_init__(self):
        """Set worker ID if not provided."""
        if self.worker_id is None:
            self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "repo_path": self.repo_path,
            "remote_url": self.remote_url,
            "branch": self.branch,
            "worker_id": self.worker_id,
            "poll_interval_seconds": self.poll_interval_seconds,
            "default_priority": self.default_priority,
            "default_timeout_seconds": self.default_timeout_seconds,
            "default_max_retries": self.default_max_retries,
            "auto_sync": self.auto_sync,
            "sync_interval_seconds": self.sync_interval_seconds,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "task_history_limit": self.task_history_limit,
            "git_author_name": self.git_author_name,
            "git_author_email": self.git_author_email,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GNAPConfig":
        """Create from dictionary."""
        return cls(
            repo_path=data.get("repo_path", ".gnap"),
            remote_url=data.get("remote_url"),
            branch=data.get("branch", "tasks"),
            worker_id=data.get("worker_id"),
            poll_interval_seconds=data.get("poll_interval_seconds", 5.0),
            default_priority=data.get("default_priority", 1),
            default_timeout_seconds=data.get("default_timeout_seconds"),
            default_max_retries=data.get("default_max_retries", 3),
            auto_sync=data.get("auto_sync", True),
            sync_interval_seconds=data.get("sync_interval_seconds", 60.0),
            max_concurrent_tasks=data.get("max_concurrent_tasks", 4),
            task_history_limit=data.get("task_history_limit", 1000),
            git_author_name=data.get("git_author_name", "GNAP Agent"),
            git_author_email=data.get("git_author_email", "gnap@praisonai.com"),
        )