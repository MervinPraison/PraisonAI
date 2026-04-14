"""Task Message Sink Protocols for PraisonAI Agents.

Provides pluggable persistence for sequenced task execution messages.
Matches Multica's ReportTaskMessages pattern but as a protocol,
enabling replay of agent output, tool calls, errors, and status changes.

Usage:
    from praisonaiagents.task.message_sink import InMemoryTaskMessageSink, TaskMessageEmitter
    
    sink = InMemoryTaskMessageSink()
    emitter = TaskMessageEmitter(task_id="t1", sink=sink, agent_name="researcher")
    emitter.emit("agent_output", "Hello world")
    emitter.emit("tool_call", "search_web('AI trends')")
    
    # Replay
    messages = sink.replay("t1")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable, List, Optional, Dict, Any


@dataclass
class TaskMessage:
    """A single sequenced message from task execution.
    
    Attributes:
        task_id: Task this message belongs to
        seq_num: Sequence number for ordering (0-indexed)
        msg_type: Message type (agent_output, tool_call, tool_result, error, status)
        content: Message content
        agent_name: Agent that produced this message
        metadata: Optional extra metadata
        timestamp: ISO timestamp
    """
    task_id: str
    seq_num: int
    msg_type: str
    content: str
    agent_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "seq_num": self.seq_num,
            "msg_type": self.msg_type,
            "content": self.content,
            "agent_name": self.agent_name,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@runtime_checkable
class TaskMessageSinkProtocol(Protocol):
    """Protocol for persisting task execution messages.
    
    Implementations can write to databases, files, WebSockets, etc.
    """

    def emit(self, message: TaskMessage) -> None:
        """Persist a single task message."""
        ...

    def replay(self, task_id: str) -> List[TaskMessage]:
        """Replay all messages for a task, ordered by seq_num."""
        ...


class NoOpTaskMessageSink:
    """Default sink that does nothing. Zero overhead."""

    def emit(self, message: TaskMessage) -> None:
        pass

    def replay(self, task_id: str) -> List[TaskMessage]:
        return []


class InMemoryTaskMessageSink:
    """In-memory sink for testing and debugging.
    
    Stores all messages in a list for inspection and replay.
    """

    def __init__(self):
        self.messages: List[TaskMessage] = []

    def emit(self, message: TaskMessage) -> None:
        self.messages.append(message)

    def replay(self, task_id: str) -> List[TaskMessage]:
        """Replay messages for a task, ordered by seq_num."""
        task_messages = [m for m in self.messages if m.task_id == task_id]
        return sorted(task_messages, key=lambda m: m.seq_num)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()


class TaskMessageEmitter:
    """Convenience emitter that auto-sequences messages for a task.
    
    Maintains a per-task sequence counter so callers don't need
    to track seq_num manually.
    
    Usage:
        emitter = TaskMessageEmitter(task_id="t1", sink=sink)
        emitter.emit("agent_output", "Hello")   # seq_num=0
        emitter.emit("tool_call", "search()")    # seq_num=1
    """

    def __init__(
        self,
        task_id: str,
        sink: TaskMessageSinkProtocol,
        agent_name: Optional[str] = None,
    ):
        self.task_id = task_id
        self.sink = sink
        self.agent_name = agent_name
        self._seq_num = 0

    def emit(
        self,
        msg_type: str,
        content: str,
        agent_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a message with auto-incremented sequence number."""
        message = TaskMessage(
            task_id=self.task_id,
            seq_num=self._seq_num,
            msg_type=msg_type,
            content=content,
            agent_name=agent_name or self.agent_name,
            metadata=metadata or {},
        )
        self.sink.emit(message)
        self._seq_num += 1
