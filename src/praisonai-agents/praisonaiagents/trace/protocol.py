"""
Action Trace Protocol for PraisonAI Agents.

Lightweight protocol for tracing agent actions. Uses only stdlib
to ensure zero dependencies and minimal overhead.

Schema Version: 1.0
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# Schema version for forward compatibility
SCHEMA_VERSION = "1.0"


class ActionEventType(str, Enum):
    """Types of action events."""
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    TOOL_START = "tool_start"
    TOOL_END = "tool_end"
    ERROR = "error"
    OUTPUT = "output"


@dataclass
class ActionEvent:
    """
    Lightweight action trace event.
    
    Represents a single action in the agent execution trace.
    Designed for minimal memory footprint and fast serialization.
    """
    event_type: str
    timestamp: float
    schema_version: str = SCHEMA_VERSION
    agent_id: Optional[str] = None
    agent_name: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result_summary: Optional[str] = None
    duration_ms: Optional[float] = None
    status: Optional[str] = None  # ok, error
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = {
            "schema_version": self.schema_version,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
        }
        
        # Add optional fields only if set
        if self.agent_id is not None:
            result["agent_id"] = self.agent_id
        if self.agent_name is not None:
            result["agent_name"] = self.agent_name
        if self.tool_name is not None:
            result["tool_name"] = self.tool_name
        if self.tool_args is not None:
            result["tool_args"] = self.tool_args
        if self.tool_result_summary is not None:
            result["tool_result_summary"] = self.tool_result_summary
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.status is not None:
            result["status"] = self.status
        if self.error_message is not None:
            result["error_message"] = self.error_message
        if self.metadata:
            result["metadata"] = self.metadata
        
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


@runtime_checkable
class TraceSinkProtocol(Protocol):
    """
    Protocol for trace event sinks.
    
    Implementations receive action events and handle them
    (e.g., print to stdout, write to file, send to server).
    
    Naming follows AGENTS.md convention: XProtocol for interfaces.
    """
    
    def emit(self, event: ActionEvent) -> None:
        """Emit an action event."""
        ...
    
    def flush(self) -> None:
        """Flush any buffered events."""
        ...
    
    def close(self) -> None:
        """Close the sink and release resources."""
        ...


# Backward compatibility alias (deprecated)
TraceSink = TraceSinkProtocol


class NoOpSink:
    """
    No-operation sink that discards all events.
    
    Used as the default sink when tracing is disabled.
    Has near-zero overhead.
    """
    
    __slots__ = ()
    
    def emit(self, event: ActionEvent) -> None:
        """Discard the event."""
        pass
    
    def flush(self) -> None:
        """No-op."""
        pass
    
    def close(self) -> None:
        """No-op."""
        pass


class ListSink:
    """
    Sink that collects events in a list.
    
    Useful for testing and programmatic access to trace events.
    """
    
    __slots__ = ("_events",)
    
    def __init__(self):
        self._events: List[ActionEvent] = []
    
    def emit(self, event: ActionEvent) -> None:
        """Add event to the list."""
        self._events.append(event)
    
    def flush(self) -> None:
        """No-op for list sink."""
        pass
    
    def close(self) -> None:
        """No-op for list sink."""
        pass
    
    def get_events(self) -> List[ActionEvent]:
        """Get all collected events."""
        return self._events.copy()
    
    def clear(self) -> None:
        """Clear all collected events."""
        self._events.clear()


@dataclass
class ActionTraceConfig:
    """
    Configuration for action tracing.
    
    Usage:
        # Default (disabled)
        config = ActionTraceConfig()
        
        # Enable with stdout
        config = ActionTraceConfig(enabled=True, sink_type="stdout")
        
        # Enable with JSONL file
        config = ActionTraceConfig(
            enabled=True,
            sink_type="jsonl",
            file_path="trace.jsonl",
        )
    """
    enabled: bool = True
    redact: bool = True
    compact: bool = False
    sink_type: str = "noop"  # noop, stdout, jsonl, file
    file_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "redact": self.redact,
            "compact": self.compact,
            "sink_type": self.sink_type,
            "file_path": self.file_path,
        }


class TraceEmitter:
    """
    Emitter for action trace events.
    
    Provides a high-level API for emitting trace events.
    Handles redaction and sink management.
    
    Usage:
        sink = ListSink()
        emitter = TraceEmitter(sink=sink)
        
        emitter.agent_start("researcher")
        emitter.tool_start("search", {"query": "AI"})
        emitter.tool_end("search", duration_ms=100, status="ok")
        emitter.agent_end("researcher", duration_ms=500)
    """
    
    __slots__ = ("_sink", "_enabled", "_redact", "_agent_starts")
    
    def __init__(
        self,
        sink: Optional[TraceSink] = None,
        enabled: bool = True,
        redact: bool = True,
    ):
        self._sink = sink or NoOpSink()
        self._enabled = enabled
        self._redact = redact
        self._agent_starts: Dict[str, float] = {}  # Track agent start times
    
    def _emit(self, event: ActionEvent) -> None:
        """Internal emit with enabled check."""
        if not self._enabled:
            return
        self._sink.emit(event)
    
    def _redact_args(self, args: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Redact sensitive data from args if enabled."""
        if args is None or not self._redact:
            return args
        
        from .redact import redact_dict
        return redact_dict(args)
    
    def agent_start(
        self,
        agent_name: str,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent start event."""
        ts = time.time()
        self._agent_starts[agent_name] = ts
        
        self._emit(ActionEvent(
            event_type=ActionEventType.AGENT_START.value,
            timestamp=ts,
            agent_name=agent_name,
            agent_id=agent_id,
            metadata=metadata or {},
        ))
    
    def agent_end(
        self,
        agent_name: str,
        agent_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        status: str = "ok",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit agent end event."""
        ts = time.time()
        
        # Calculate duration if not provided
        if duration_ms is None and agent_name in self._agent_starts:
            start_ts = self._agent_starts.pop(agent_name, None)
            if start_ts:
                duration_ms = (ts - start_ts) * 1000
        
        self._emit(ActionEvent(
            event_type=ActionEventType.AGENT_END.value,
            timestamp=ts,
            agent_name=agent_name,
            agent_id=agent_id,
            duration_ms=duration_ms,
            status=status,
            metadata=metadata or {},
        ))
    
    def tool_start(
        self,
        tool_name: str,
        tool_args: Optional[Dict[str, Any]] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit tool start event."""
        self._emit(ActionEvent(
            event_type=ActionEventType.TOOL_START.value,
            timestamp=time.time(),
            tool_name=tool_name,
            tool_args=self._redact_args(tool_args),
            agent_name=agent_name,
            agent_id=agent_id,
            metadata=metadata or {},
        ))
    
    def tool_end(
        self,
        tool_name: str,
        duration_ms: float,
        status: str = "ok",
        result_summary: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit tool end event."""
        self._emit(ActionEvent(
            event_type=ActionEventType.TOOL_END.value,
            timestamp=time.time(),
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            tool_result_summary=result_summary,
            agent_name=agent_name,
            agent_id=agent_id,
            error_message=error_message,
            metadata=metadata or {},
        ))
    
    def error(
        self,
        message: str,
        tool_name: Optional[str] = None,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit error event."""
        self._emit(ActionEvent(
            event_type=ActionEventType.ERROR.value,
            timestamp=time.time(),
            error_message=message,
            tool_name=tool_name,
            agent_name=agent_name,
            agent_id=agent_id,
            status="error",
            metadata=metadata or {},
        ))
    
    def output(
        self,
        content: str,
        agent_name: Optional[str] = None,
        agent_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit final output event."""
        # Truncate long output for summary
        summary = content[:500] + "..." if len(content) > 500 else content
        
        self._emit(ActionEvent(
            event_type=ActionEventType.OUTPUT.value,
            timestamp=time.time(),
            tool_result_summary=summary,
            agent_name=agent_name,
            agent_id=agent_id,
            metadata=metadata or {},
        ))
    
    def flush(self) -> None:
        """Flush the sink."""
        self._sink.flush()
    
    def close(self) -> None:
        """Close the sink."""
        self._sink.close()


# Global default emitter (NoOp by default)
_default_emitter: Optional[TraceEmitter] = None


def get_default_emitter() -> TraceEmitter:
    """Get the default trace emitter."""
    global _default_emitter
    if _default_emitter is None:
        _default_emitter = TraceEmitter(sink=NoOpSink(), enabled=False)
    return _default_emitter


def set_default_emitter(emitter: TraceEmitter) -> None:
    """Set the default trace emitter."""
    global _default_emitter
    _default_emitter = emitter
