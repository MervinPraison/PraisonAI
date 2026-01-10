"""
StreamEvent protocol for PraisonAI streaming.

This module defines the minimal streaming event protocol that both OpenAI SDK
and LiteLLM streaming paths map their native chunks/events into.

Design principles:
- Zero overhead when not used (lazy imports, no global state)
- Multi-agent safe (per-agent callbacks, no shared mutable state)
- Async-safe (separate sync/async callback interfaces)
- Provider-agnostic (same events for OpenAI, LiteLLM, etc.)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
import time


class StreamEventType(Enum):
    """Types of streaming events emitted during LLM response streaming."""
    
    REQUEST_START = "request_start"      # Before API call is made
    HEADERS_RECEIVED = "headers_received"  # When HTTP 200 headers arrive
    FIRST_TOKEN = "first_token"          # First content delta received (TTFT marker)
    DELTA_TEXT = "delta_text"            # Text content delta
    DELTA_TOOL_CALL = "delta_tool_call"  # Tool call delta (function name, args chunk)
    TOOL_CALL_END = "tool_call_end"      # Tool call complete
    LAST_TOKEN = "last_token"            # Final content delta
    STREAM_END = "stream_end"            # Stream completed successfully
    ERROR = "error"                      # Error during streaming


@dataclass
class StreamEvent:
    """
    A single streaming event emitted during LLM response streaming.
    
    Attributes:
        type: The type of event (see StreamEventType)
        timestamp: High-precision timestamp (time.perf_counter())
        content: Text content for DELTA_TEXT events
        tool_call: Tool call data for DELTA_TOOL_CALL events
        metadata: Additional event-specific metadata
        error: Error message for ERROR events
    """
    type: StreamEventType
    timestamp: float = field(default_factory=time.perf_counter)
    content: Optional[str] = None
    tool_call: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def __repr__(self) -> str:
        parts = [f"StreamEvent({self.type.value}"]
        if self.content:
            preview = self.content[:20] + "..." if len(self.content) > 20 else self.content
            parts.append(f", content={preview!r}")
        if self.tool_call:
            parts.append(f", tool_call={self.tool_call.get('name', 'unknown')}")
        if self.error:
            parts.append(f", error={self.error!r}")
        parts.append(")")
        return "".join(parts)


class StreamCallback(Protocol):
    """Protocol for synchronous stream event callbacks."""
    
    def __call__(self, event: StreamEvent) -> None:
        """Called when a stream event is emitted."""
        ...


class AsyncStreamCallback(Protocol):
    """Protocol for asynchronous stream event callbacks."""
    
    async def __call__(self, event: StreamEvent) -> None:
        """Called when a stream event is emitted (async)."""
        ...


@dataclass
class StreamMetrics:
    """
    Timing metrics for a streaming response.
    
    Tracks key timestamps to measure:
    - TTFT (Time To First Token): How long until first token arrives
    - Stream Duration: How long the token streaming takes
    - Total Time: End-to-end request time
    
    All times are in seconds, measured with time.perf_counter() for precision.
    """
    request_start: float = 0.0
    headers_received: float = 0.0
    first_token: float = 0.0
    last_token: float = 0.0
    stream_end: float = 0.0
    token_count: int = 0
    
    @property
    def ttft(self) -> float:
        """Time To First Token in seconds (first_token - request_start)."""
        if self.first_token and self.request_start:
            return self.first_token - self.request_start
        return 0.0
    
    @property
    def stream_duration(self) -> float:
        """Duration of token streaming in seconds (last_token - first_token)."""
        if self.last_token and self.first_token:
            return self.last_token - self.first_token
        return 0.0
    
    @property
    def total_time(self) -> float:
        """Total request time in seconds (stream_end - request_start)."""
        if self.stream_end and self.request_start:
            return self.stream_end - self.request_start
        return 0.0
    
    @property
    def tokens_per_second(self) -> float:
        """Token generation rate (tokens / stream_duration)."""
        if self.stream_duration > 0 and self.token_count > 0:
            return self.token_count / self.stream_duration
        return 0.0
    
    def update_from_event(self, event: StreamEvent) -> None:
        """Update metrics from a StreamEvent."""
        if event.type == StreamEventType.REQUEST_START:
            self.request_start = event.timestamp
        elif event.type == StreamEventType.HEADERS_RECEIVED:
            self.headers_received = event.timestamp
        elif event.type == StreamEventType.FIRST_TOKEN:
            self.first_token = event.timestamp
            self.token_count = 1
        elif event.type == StreamEventType.DELTA_TEXT:
            self.token_count += 1
        elif event.type == StreamEventType.LAST_TOKEN:
            self.last_token = event.timestamp
        elif event.type == StreamEventType.STREAM_END:
            self.stream_end = event.timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for logging/display."""
        return {
            "ttft_ms": round(self.ttft * 1000, 1),
            "stream_duration_ms": round(self.stream_duration * 1000, 1),
            "total_time_ms": round(self.total_time * 1000, 1),
            "token_count": self.token_count,
            "tokens_per_second": round(self.tokens_per_second, 1),
        }
    
    def format_summary(self) -> str:
        """Format metrics as a human-readable summary string."""
        return (
            f"TTFT: {self.ttft*1000:.0f}ms | "
            f"Stream: {self.stream_duration*1000:.0f}ms | "
            f"Total: {self.total_time*1000:.0f}ms | "
            f"Tokens: {self.token_count} ({self.tokens_per_second:.1f}/s)"
        )


class StreamEventEmitter:
    """
    Manages stream event callbacks for an agent or streaming session.
    
    Thread-safe and multi-agent safe - each agent has its own emitter instance.
    Supports both sync and async callbacks.
    
    Usage:
        emitter = StreamEventEmitter()
        emitter.add_callback(my_callback)
        
        # During streaming:
        emitter.emit(StreamEvent(type=StreamEventType.DELTA_TEXT, content="Hello"))
    """
    
    def __init__(self) -> None:
        self._callbacks: List[StreamCallback] = []
        self._async_callbacks: List[AsyncStreamCallback] = []
        self._metrics: Optional[StreamMetrics] = None
        self._collect_metrics: bool = False
    
    def add_callback(self, callback: StreamCallback) -> None:
        """Add a synchronous callback to receive stream events."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: StreamCallback) -> None:
        """Remove a synchronous callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def add_async_callback(self, callback: AsyncStreamCallback) -> None:
        """Add an asynchronous callback to receive stream events."""
        self._async_callbacks.append(callback)
    
    def remove_async_callback(self, callback: AsyncStreamCallback) -> None:
        """Remove an asynchronous callback."""
        if callback in self._async_callbacks:
            self._async_callbacks.remove(callback)
    
    def enable_metrics(self) -> None:
        """Enable metrics collection for this streaming session."""
        self._collect_metrics = True
        self._metrics = StreamMetrics()
    
    def get_metrics(self) -> Optional[StreamMetrics]:
        """Get collected metrics (None if metrics not enabled)."""
        return self._metrics
    
    def reset_metrics(self) -> None:
        """Reset metrics for a new streaming session."""
        if self._collect_metrics:
            self._metrics = StreamMetrics()
    
    def emit(self, event: StreamEvent) -> None:
        """
        Emit a stream event to all registered callbacks.
        
        This is the synchronous emission path. For async streaming,
        use emit_async().
        """
        # Update metrics if enabled
        if self._collect_metrics and self._metrics:
            self._metrics.update_from_event(event)
        
        # Call all sync callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception:
                # Don't let callback errors break streaming
                pass
    
    async def emit_async(self, event: StreamEvent) -> None:
        """
        Emit a stream event to all registered callbacks (async version).
        
        Calls both sync and async callbacks.
        """
        # Update metrics if enabled
        if self._collect_metrics and self._metrics:
            self._metrics.update_from_event(event)
        
        # Call sync callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception:
                pass
        
        # Call async callbacks
        for callback in self._async_callbacks:
            try:
                await callback(event)
            except Exception:
                pass
    
    @property
    def has_callbacks(self) -> bool:
        """Check if any callbacks are registered."""
        return bool(self._callbacks or self._async_callbacks)


def create_text_printer_callback(flush: bool = True) -> StreamCallback:
    """
    Create a simple callback that prints text deltas to stdout.
    
    Args:
        flush: Whether to flush stdout after each print (default True)
    
    Returns:
        A StreamCallback that prints DELTA_TEXT content
    """
    def printer(event: StreamEvent) -> None:
        if event.type == StreamEventType.DELTA_TEXT and event.content:
            print(event.content, end="", flush=flush)
        elif event.type == StreamEventType.STREAM_END:
            print()  # Newline at end
    
    return printer


def create_metrics_callback(metrics: StreamMetrics) -> StreamCallback:
    """
    Create a callback that updates a StreamMetrics instance.
    
    Args:
        metrics: The StreamMetrics instance to update
    
    Returns:
        A StreamCallback that updates the metrics
    """
    def updater(event: StreamEvent) -> None:
        metrics.update_from_event(event)
    
    return updater
