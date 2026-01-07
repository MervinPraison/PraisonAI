"""
Event definitions for the Event Bus.

Provides typed event structures for the publish/subscribe system.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum
import time
import uuid


class EventType(str, Enum):
    """Standard event types for the agent system."""
    
    # Session events
    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    SESSION_DELETED = "session.deleted"
    SESSION_FORKED = "session.forked"
    SESSION_REVERTED = "session.reverted"
    
    # Message events
    MESSAGE_CREATED = "message.created"
    MESSAGE_UPDATED = "message.updated"
    MESSAGE_PART_CREATED = "message.part.created"
    MESSAGE_PART_UPDATED = "message.part.updated"
    
    # Permission events
    PERMISSION_ASKED = "permission.asked"
    PERMISSION_REPLIED = "permission.replied"
    
    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_ERROR = "agent.error"
    
    # Tool events
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_ERROR = "tool.error"
    
    # Snapshot events
    SNAPSHOT_CREATED = "snapshot.created"
    SNAPSHOT_RESTORED = "snapshot.restored"
    
    # Server events
    SERVER_STARTED = "server.started"
    SERVER_STOPPED = "server.stopped"
    CLIENT_CONNECTED = "client.connected"
    CLIENT_DISCONNECTED = "client.disconnected"
    
    # Compaction events
    COMPACTION_STARTED = "compaction.started"
    COMPACTION_COMPLETED = "compaction.completed"
    
    # Custom event (for user-defined events)
    CUSTOM = "custom"


@dataclass
class Event:
    """
    A typed event for the event bus.
    
    Attributes:
        type: The event type (from EventType enum or custom string)
        data: The event payload data
        id: Unique event identifier
        timestamp: Unix timestamp when event was created
        source: Optional source identifier (e.g., session_id, agent_name)
        metadata: Optional additional metadata
    """
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data.get("type", EventType.CUSTOM.value),
            data=data.get("data", {}),
            timestamp=data.get("timestamp", time.time()),
            source=data.get("source"),
            metadata=data.get("metadata", {}),
        )
    
    def to_sse(self) -> str:
        """Format event for Server-Sent Events."""
        import json
        return f"id: {self.id}\nevent: {self.type}\ndata: {json.dumps(self.to_dict())}\n\n"
    
    def __repr__(self) -> str:
        return f"Event(type={self.type!r}, id={self.id[:8]}..., source={self.source!r})"
