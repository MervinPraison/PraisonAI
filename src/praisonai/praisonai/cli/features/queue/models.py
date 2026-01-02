"""
Data models for the PraisonAI Queue System.

Defines QueuedRun, RunState, RunPriority, and QueueConfig.
"""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional
import time
import uuid


class RunState(str, Enum):
    """State of a queued run."""
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    def is_terminal(self) -> bool:
        """Check if this is a terminal state."""
        return self in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED)
    
    def is_active(self) -> bool:
        """Check if this is an active (non-terminal) state."""
        return not self.is_terminal()


class RunPriority(IntEnum):
    """Priority levels for queued runs. Higher value = higher priority."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3
    
    @classmethod
    def from_string(cls, s: str) -> "RunPriority":
        """Parse priority from string."""
        mapping = {
            "low": cls.LOW,
            "normal": cls.NORMAL,
            "high": cls.HIGH,
            "urgent": cls.URGENT,
        }
        return mapping.get(s.lower(), cls.NORMAL)


@dataclass
class QueuedRun:
    """A single queued agent run."""
    
    # Identity
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_name: str = ""
    input_content: str = ""
    
    # State
    state: RunState = RunState.QUEUED
    priority: RunPriority = RunPriority.NORMAL
    
    # Attribution / tracing
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    workspace: Optional[str] = None
    user_id: Optional[str] = None
    
    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    
    # Results
    output_content: Optional[str] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Retry tracking
    retry_count: int = 0
    max_retries: int = 3
    parent_run_id: Optional[str] = None  # Link to original run if this is a retry
    
    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Chat history for session continuity
    chat_history: List[Dict[str, str]] = field(default_factory=list)
    
    # Streaming state
    output_chunks: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Ensure proper types after initialization."""
        if isinstance(self.state, str):
            self.state = RunState(self.state)
        if isinstance(self.priority, int) and not isinstance(self.priority, RunPriority):
            self.priority = RunPriority(self.priority)
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Get run duration in seconds."""
        if self.started_at is None:
            return None
        end = self.ended_at or time.time()
        return end - self.started_at
    
    @property
    def wait_seconds(self) -> float:
        """Get time spent waiting in queue."""
        start = self.started_at or time.time()
        return start - self.created_at
    
    def can_retry(self) -> bool:
        """Check if this run can be retried."""
        return (
            self.state == RunState.FAILED and
            self.retry_count < self.max_retries
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "input_content": self.input_content,
            "state": self.state.value,
            "priority": int(self.priority),
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "workspace": self.workspace,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "output_content": self.output_content,
            "error": self.error,
            "metrics": self.metrics,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "parent_run_id": self.parent_run_id,
            "config": self.config,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueuedRun":
        """Create from dictionary."""
        # Handle state conversion
        state = data.get("state", "queued")
        if isinstance(state, str):
            state = RunState(state)
        
        # Handle priority conversion
        priority = data.get("priority", 1)
        if isinstance(priority, int):
            priority = RunPriority(priority)
        
        return cls(
            run_id=data.get("run_id", str(uuid.uuid4())[:8]),
            agent_name=data.get("agent_name", ""),
            input_content=data.get("input_content", ""),
            state=state,
            priority=priority,
            session_id=data.get("session_id"),
            trace_id=data.get("trace_id"),
            workspace=data.get("workspace"),
            user_id=data.get("user_id"),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            output_content=data.get("output_content"),
            error=data.get("error"),
            metrics=data.get("metrics", {}),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            parent_run_id=data.get("parent_run_id"),
            config=data.get("config", {}),
        )


@dataclass
class QueueConfig:
    """Configuration for the queue system."""
    
    # Concurrency limits
    max_concurrent_global: int = 4
    max_concurrent_per_agent: int = 2
    max_concurrent_per_workspace: int = 4
    
    # Queue limits
    max_queue_size: int = 100
    
    # Defaults
    default_priority: RunPriority = RunPriority.NORMAL
    default_max_retries: int = 3
    
    # Persistence
    enable_persistence: bool = True
    db_path: str = ".praison/queue.db"
    
    # Autosave
    autosave_interval_seconds: float = 30.0
    
    # Backpressure
    stream_buffer_size: int = 1000
    drop_strategy: str = "oldest"  # "oldest" or "newest"
    
    # Timeouts
    run_timeout_seconds: Optional[float] = None  # None = no timeout
    worker_poll_interval: float = 0.1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_concurrent_global": self.max_concurrent_global,
            "max_concurrent_per_agent": self.max_concurrent_per_agent,
            "max_concurrent_per_workspace": self.max_concurrent_per_workspace,
            "max_queue_size": self.max_queue_size,
            "default_priority": int(self.default_priority),
            "default_max_retries": self.default_max_retries,
            "enable_persistence": self.enable_persistence,
            "db_path": self.db_path,
            "autosave_interval_seconds": self.autosave_interval_seconds,
            "stream_buffer_size": self.stream_buffer_size,
            "drop_strategy": self.drop_strategy,
            "run_timeout_seconds": self.run_timeout_seconds,
            "worker_poll_interval": self.worker_poll_interval,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueConfig":
        """Create from dictionary."""
        priority = data.get("default_priority", 1)
        if isinstance(priority, int):
            priority = RunPriority(priority)
        
        return cls(
            max_concurrent_global=data.get("max_concurrent_global", 4),
            max_concurrent_per_agent=data.get("max_concurrent_per_agent", 2),
            max_concurrent_per_workspace=data.get("max_concurrent_per_workspace", 4),
            max_queue_size=data.get("max_queue_size", 100),
            default_priority=priority,
            default_max_retries=data.get("default_max_retries", 3),
            enable_persistence=data.get("enable_persistence", True),
            db_path=data.get("db_path", ".praison/queue.db"),
            autosave_interval_seconds=data.get("autosave_interval_seconds", 30.0),
            stream_buffer_size=data.get("stream_buffer_size", 1000),
            drop_strategy=data.get("drop_strategy", "oldest"),
            run_timeout_seconds=data.get("run_timeout_seconds"),
            worker_poll_interval=data.get("worker_poll_interval", 0.1),
        )


@dataclass
class QueueStats:
    """Statistics about the queue."""
    queued_count: int = 0
    running_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    cancelled_count: int = 0
    total_runs: int = 0
    avg_wait_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    
    @property
    def active_count(self) -> int:
        """Count of active (non-terminal) runs."""
        return self.queued_count + self.running_count


@dataclass 
class StreamChunk:
    """A chunk of streaming output."""
    run_id: str
    content: str
    timestamp: float = field(default_factory=time.time)
    chunk_index: int = 0
    is_final: bool = False
    
    
@dataclass
class QueueEvent:
    """An event from the queue system."""
    event_type: str  # "run_started", "run_completed", "run_failed", "output_chunk", "state_changed"
    run_id: str
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)
