"""
Context Events for PraisonAI Agents.

Provides context-level tracing for replay functionality.
Tracks context changes during agent execution for debugging and replay.

Zero Performance Impact:
- NoOpSink is the default (zero overhead when not used)
- Disabled emitter has near-zero overhead
- Uses __slots__ for memory efficiency

Schema Version: 1.0
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
import json


CONTEXT_SCHEMA_VERSION = "1.0"


class ContextEventType(str, Enum):
    """Types of context events for replay."""
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_HANDOFF = "agent_handoff"
    MESSAGE_ADDED = "message_added"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    CONTEXT_SNAPSHOT = "context_snapshot"


@dataclass
class ContextEvent:
    """
    A single context event for replay.
    
    Represents a discrete change in agent context during execution.
    Designed for minimal memory footprint and fast serialization.
    
    Attributes:
        event_type: Type of context event
        timestamp: Unix timestamp when event occurred
        session_id: Session identifier for grouping events
        agent_name: Name of the agent (if applicable)
        sequence_num: Sequential event number within session
        messages_count: Number of messages in context at this point
        tokens_used: Tokens used in context at this point
        tokens_budget: Total token budget available
        data: Event-specific data (tool args, message content, etc.)
    """
    event_type: ContextEventType
    timestamp: float
    session_id: str
    agent_name: Optional[str] = None
    sequence_num: int = 0
    messages_count: int = 0
    tokens_used: int = 0
    tokens_budget: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "event_type": self.event_type.value if isinstance(self.event_type, ContextEventType) else self.event_type,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "sequence_num": self.sequence_num,
            "messages_count": self.messages_count,
            "tokens_used": self.tokens_used,
            "tokens_budget": self.tokens_budget,
            "data": self.data,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextEvent":
        """Create ContextEvent from dictionary."""
        event_type_str = data.get("event_type", "")
        
        # Convert string to enum
        try:
            event_type = ContextEventType(event_type_str)
        except ValueError:
            # Fallback for unknown event types
            event_type = ContextEventType.CONTEXT_SNAPSHOT
        
        return cls(
            event_type=event_type,
            timestamp=data.get("timestamp", 0.0),
            session_id=data.get("session_id", ""),
            agent_name=data.get("agent_name"),
            sequence_num=data.get("sequence_num", 0),
            messages_count=data.get("messages_count", 0),
            tokens_used=data.get("tokens_used", 0),
            tokens_budget=data.get("tokens_budget", 0),
            data=data.get("data", {}),
        )


@runtime_checkable
class ContextTraceSink(Protocol):
    """
    Protocol for context trace event sinks.
    
    Implementations receive context events and handle them
    (e.g., write to file, collect in memory, send to server).
    """
    
    def emit(self, event: ContextEvent) -> None:
        """Emit a context event."""
        ...
    
    def flush(self) -> None:
        """Flush any buffered events."""
        ...
    
    def close(self) -> None:
        """Close the sink and release resources."""
        ...


class ContextNoOpSink:
    """
    No-operation sink that discards all events.
    
    Used as the default sink when context tracing is disabled.
    Has near-zero overhead.
    """
    
    __slots__ = ()
    
    def emit(self, event: ContextEvent) -> None:
        """Discard the event."""
        pass
    
    def flush(self) -> None:
        """No-op."""
        pass
    
    def close(self) -> None:
        """No-op."""
        pass


class ContextListSink:
    """
    Sink that collects events in a list.
    
    Useful for testing and programmatic access to context events.
    """
    
    __slots__ = ("_events",)
    
    def __init__(self):
        self._events: List[ContextEvent] = []
    
    def emit(self, event: ContextEvent) -> None:
        """Add event to the list."""
        self._events.append(event)
    
    def flush(self) -> None:
        """No-op for list sink."""
        pass
    
    def close(self) -> None:
        """No-op for list sink."""
        pass
    
    def get_events(self) -> List[ContextEvent]:
        """Get all collected events."""
        return self._events.copy()
    
    def clear(self) -> None:
        """Clear all collected events."""
        self._events.clear()
    
    def __len__(self) -> int:
        """Return number of events."""
        return len(self._events)
    
    def __iter__(self):
        """Iterate over events."""
        return iter(self._events)


class ContextTraceEmitter:
    """
    Emitter for context trace events.
    
    Provides a high-level API for emitting context events during
    agent execution. Handles sequence numbering and redaction.
    
    Usage:
        sink = ContextListSink()
        emitter = ContextTraceEmitter(sink=sink, session_id="my-session")
        
        emitter.session_start()
        emitter.agent_start("researcher")
        emitter.message_added("researcher", "user", "Hello", 1, 10)
        emitter.agent_end("researcher")
        emitter.session_end()
    """
    
    __slots__ = ("_sink", "_session_id", "_enabled", "_redact", "_sequence")
    
    def __init__(
        self,
        sink: Optional[ContextTraceSink] = None,
        session_id: str = "",
        enabled: bool = True,
        redact: bool = True,
    ):
        """
        Initialize context trace emitter.
        
        Args:
            sink: Sink to emit events to (default: ContextNoOpSink)
            session_id: Session identifier for all events
            enabled: Whether tracing is enabled
            redact: Whether to redact sensitive data
        """
        self._sink = sink if sink is not None else ContextNoOpSink()
        self._session_id = session_id
        self._enabled = enabled
        self._redact = redact
        self._sequence = 0
    
    def _emit(self, event: ContextEvent) -> None:
        """Internal emit with enabled check and sequence assignment."""
        if not self._enabled:
            return
        event.sequence_num = self._sequence
        self._sequence += 1
        self._sink.emit(event)
    
    def _redact_dict(self, data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Redact sensitive data from dictionary if enabled."""
        if data is None or not self._redact:
            return data
        
        from .redact import redact_dict
        return redact_dict(data)
    
    def session_start(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit session start event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.SESSION_START,
            timestamp=time.time(),
            session_id=self._session_id,
            data=metadata or {},
        ))
    
    def session_end(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Emit session end event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.SESSION_END,
            timestamp=time.time(),
            session_id=self._session_id,
            data=metadata or {},
        ))
    
    def agent_start(
        self,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent start event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.AGENT_START,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data=metadata or {},
        ))
    
    def agent_end(
        self,
        agent_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent end event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.AGENT_END,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data=metadata or {},
        ))
    
    def message_added(
        self,
        agent_name: str,
        role: str,
        content: str,
        messages_count: int,
        tokens_used: int,
        tokens_budget: int = 0,
    ) -> None:
        """Emit message added event."""
        # Truncate long content for storage
        truncated_content = content[:1000] + "..." if len(content) > 1000 else content
        
        self._emit(ContextEvent(
            event_type=ContextEventType.MESSAGE_ADDED,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            messages_count=messages_count,
            tokens_used=tokens_used,
            tokens_budget=tokens_budget,
            data={
                "role": role,
                "content": truncated_content,
            },
        ))
    
    def tool_call_start(
        self,
        agent_name: str,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit tool call start event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.TOOL_CALL_START,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "tool_name": tool_name,
                "tool_args": self._redact_dict(tool_args) if tool_args else {},
            },
        ))
    
    def tool_call_end(
        self,
        agent_name: str,
        tool_name: str,
        result: Optional[str] = None,
        duration_ms: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        """Emit tool call end event."""
        # Truncate long results
        truncated_result = None
        if result:
            truncated_result = result[:500] + "..." if len(result) > 500 else result
        
        self._emit(ContextEvent(
            event_type=ContextEventType.TOOL_CALL_END,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "tool_name": tool_name,
                "result": truncated_result,
                "duration_ms": duration_ms,
                "error": error,
            },
        ))
    
    def llm_request(
        self,
        agent_name: str,
        messages_count: int,
        tokens_used: int,
        tokens_budget: int = 0,
        model: Optional[str] = None,
    ) -> None:
        """Emit LLM request event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.LLM_REQUEST,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            messages_count=messages_count,
            tokens_used=tokens_used,
            tokens_budget=tokens_budget,
            data={
                "model": model,
            },
        ))
    
    def llm_response(
        self,
        agent_name: str,
        response_tokens: int = 0,
        duration_ms: float = 0.0,
        finish_reason: Optional[str] = None,
    ) -> None:
        """Emit LLM response event."""
        self._emit(ContextEvent(
            event_type=ContextEventType.LLM_RESPONSE,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            data={
                "response_tokens": response_tokens,
                "duration_ms": duration_ms,
                "finish_reason": finish_reason,
            },
        ))
    
    def context_snapshot(
        self,
        agent_name: str,
        messages_count: int,
        tokens_used: int,
        tokens_budget: int,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Emit context snapshot event with full context state."""
        self._emit(ContextEvent(
            event_type=ContextEventType.CONTEXT_SNAPSHOT,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=agent_name,
            messages_count=messages_count,
            tokens_used=tokens_used,
            tokens_budget=tokens_budget,
            data={
                "messages": messages or [],
            },
        ))
    
    def agent_handoff(
        self,
        from_agent: str,
        to_agent: str,
        reason: Optional[str] = None,
        context_passed: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent handoff event for tracking agent-to-agent flow."""
        self._emit(ContextEvent(
            event_type=ContextEventType.AGENT_HANDOFF,
            timestamp=time.time(),
            session_id=self._session_id,
            agent_name=from_agent,
            data={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "reason": reason,
                "context_passed": context_passed or {},
            },
        ))
    
    def flush(self) -> None:
        """Flush the sink."""
        self._sink.flush()
    
    def close(self) -> None:
        """Close the sink."""
        self._sink.close()
    
    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id
    
    @property
    def enabled(self) -> bool:
        """Check if emitter is enabled."""
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Set enabled state."""
        self._enabled = value
