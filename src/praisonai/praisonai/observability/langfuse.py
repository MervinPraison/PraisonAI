"""
Langfuse TraceSinkProtocol Implementation for PraisonAI.

Provides LangfuseSink adapter that implements TraceSinkProtocol from the core SDK,
enabling observability integration with Langfuse for agent traces, tool calls, and errors.

Architecture:
- Core SDK (praisonaiagents): Defines TraceSinkProtocol
- Wrapper (praisonai): Implements LangfuseSink adapter (this file)
- Pattern: Protocol-driven design per AGENTS.md §4.1
"""

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from praisonaiagents.trace.protocol import ActionEvent, ActionEventType, TraceSinkProtocol


@dataclass
class LangfuseSinkConfig:
    """
    Configuration for Langfuse trace sink.
    
    Follows the False=disabled, True=defaults, Config=custom pattern from AGENTS.md §5.2.
    
    Fields not explicitly provided are filled from environment variables:
      LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST (or LANGFUSE_BASE_URL).
    """
    public_key: str = ""
    secret_key: str = ""
    host: str = ""
    flush_at: int = 20
    flush_interval: float = 10.0
    enabled: bool = True
    
    def __post_init__(self):
        """Fill missing fields from environment variables."""
        import os
        if not self.public_key:
            self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        if not self.secret_key:
            self.secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        if not self.host:
            self.host = os.getenv(
                "LANGFUSE_HOST",
                os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            )


class LangfuseSink:
    """
    TraceSinkProtocol implementation for Langfuse.
    
    Maps PraisonAI ActionEvents to Langfuse v3+ observation API:
    - AGENT_START -> start_observation(as_type="span") for trace and root span
    - AGENT_END -> observation.update() + observation.end()
    - TOOL_START -> start_observation(as_type="span") for child span
    - TOOL_END -> observation.update() + observation.end()
    - ERROR -> start_observation(as_type="event", level="ERROR")
    - OUTPUT -> start_observation(as_type="event")
    
    Thread-safe: langfuse.Langfuse handles its own batching and thread safety.
    """
    
    __slots__ = ("_config", "_client", "_traces", "_spans", "_lock", "_closed")
    
    def __init__(self, config: Optional[LangfuseSinkConfig] = None):
        self._config = config or LangfuseSinkConfig()
        self._client: Optional[Any] = None  # Lazy-loaded langfuse.Langfuse
        self._traces: Dict[str, Any] = {}  # agent_name -> trace observation
        self._spans: Dict[str, Any] = {}   # span_key -> span observation
        self._lock = threading.Lock()
        self._closed = False
        
        if self._config.enabled:
            self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Lazy import and initialize Langfuse client."""
        try:
            import langfuse
            
            # Validate config
            if not (self._config.public_key and self._config.secret_key):
                raise ValueError(
                    "Langfuse credentials missing. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY "
                    "environment variables or pass them to LangfuseSinkConfig."
                )
            
            self._client = langfuse.Langfuse(
                public_key=self._config.public_key,
                secret_key=self._config.secret_key,
                host=self._config.host,
                flush_at=self._config.flush_at,
                flush_interval=self._config.flush_interval,
            )
            
        except ImportError:
            raise ImportError(
                "Langfuse is not installed. Install with: pip install praisonai[langfuse]"
            )
    
    def emit(self, event: ActionEvent) -> None:
        """Emit an action event to Langfuse."""
        if not self._config.enabled or self._closed or not self._client:
            return
        
        try:
            with self._lock:
                self._handle_event(event)
        except Exception as e:
            # Don't let observability errors break agent execution
            print(f"LangfuseSink error: {e}")
    
    def _handle_event(self, event: ActionEvent) -> None:
        """Handle a single ActionEvent (called under lock)."""
        event_type = event.event_type
        agent_name = event.agent_name or "unknown-agent"
        
        if event_type == ActionEventType.AGENT_START.value:
            self._handle_agent_start(event, agent_name)
        elif event_type == ActionEventType.AGENT_END.value:
            self._handle_agent_end(event, agent_name)
        elif event_type == ActionEventType.TOOL_START.value:
            self._handle_tool_start(event, agent_name)
        elif event_type == ActionEventType.TOOL_END.value:
            self._handle_tool_end(event, agent_name)
        elif event_type == ActionEventType.ERROR.value:
            self._handle_error(event, agent_name)
        elif event_type == ActionEventType.OUTPUT.value:
            self._handle_output(event, agent_name)
    
    def _handle_agent_start(self, event: ActionEvent, agent_name: str) -> None:
        """Handle AGENT_START -> create trace observation and root span."""
        # Create root span observation (trace is implicit in v3+)
        trace_name = f"agent-run-{agent_name}"
        trace_input = event.metadata.get("input") if event.metadata else None
        
        # Use unique agent key combining agent_id and name for collision safety
        agent_key = f"{event.agent_id or agent_name}-{agent_name}"
        
        span = self._client.start_observation(
            name=trace_name,
            as_type="span",
            input=trace_input,
            start_time=event.timestamp,
            metadata={
                "agent_id": event.agent_id,
                "agent_name": agent_name,
                "schema_version": event.schema_version,
                **(event.metadata if event.metadata else {}),
            }
        )
        # Store both trace and span reference with unique key
        self._traces[agent_key] = span  # Root span serves as trace reference
        self._spans[agent_key] = span
    
    def _handle_agent_end(self, event: ActionEvent, agent_name: str) -> None:
        """Handle AGENT_END -> end root span observation."""
        agent_key = f"{event.agent_id or agent_name}-{agent_name}"
        span = self._spans.get(agent_key)
        if span:
            span.update(
                end_time=event.timestamp,
                output=event.metadata.get("output") if event.metadata else None,
                status_message=event.status or "completed",
                level="ERROR" if event.status == "error" else "DEFAULT",
            )
            span.end()
            # Clean up
            self._spans.pop(agent_key, None)
            self._traces.pop(agent_key, None)
    
    def _handle_tool_start(self, event: ActionEvent, agent_name: str) -> None:
        """Handle TOOL_START -> create child span observation."""
        agent_key = f"{event.agent_id or agent_name}-{agent_name}"
        parent_span = self._spans.get(agent_key)
        if not parent_span:
            return
        
        tool_name = event.tool_name or "unknown-tool"
        
        # Generate unique tool invocation key with UUID for collision safety
        import uuid
        tool_invocation_id = str(uuid.uuid4())[:8]  # Short UUID
        tool_key = f"{agent_key}:{tool_name}:{tool_invocation_id}"
        
        tool_span = self._client.start_observation(
            name=tool_name,
            as_type="span",
            start_time=event.timestamp,
            input=event.tool_args,
            metadata={
                "tool_name": tool_name,
                "parent_agent": agent_name,
                "invocation_id": tool_invocation_id,
                **(event.metadata if event.metadata else {}),
            }
        )
        
        # Store with unique tool key
        self._spans[tool_key] = tool_span
    
    def _handle_tool_end(self, event: ActionEvent, agent_name: str) -> None:
        """Handle TOOL_END -> end tool span observation."""
        agent_key = f"{event.agent_id or agent_name}-{agent_name}"
        tool_name = event.tool_name or "unknown-tool"
        
        # Find the most recent matching tool span
        tool_key = None
        for key in self._spans:
            if key.startswith(f"{agent_key}:{tool_name}:") and key != agent_key:
                tool_key = key
        
        if not tool_key:
            return
        
        tool_span = self._spans.pop(tool_key, None)
        if tool_span:
            tool_span.update(
                end_time=event.timestamp,
                output=event.tool_result_summary,
                status_message=event.status or "completed",
                level="ERROR" if event.status == "error" else "DEFAULT",
                metadata={
                    "duration_ms": event.duration_ms,
                    **(event.metadata if event.metadata else {}),
                }
            )
            tool_span.end()
    
    def _handle_error(self, event: ActionEvent, agent_name: str) -> None:
        """Handle ERROR -> create error event observation."""
        agent_key = f"{event.agent_id or agent_name}-{agent_name}"
        
        error_event = self._client.start_observation(
            name="error",
            as_type="event",
            start_time=event.timestamp,
            level="ERROR",
            status_message=event.error_message,
            input=event.tool_args,
            metadata={
                "tool_name": event.tool_name,
                "agent_name": agent_name,
                **(event.metadata if event.metadata else {}),
            }
        )
        error_event.end()
    
    def _handle_output(self, event: ActionEvent, agent_name: str) -> None:
        """Handle OUTPUT -> create output event observation."""
        output_event = self._client.start_observation(
            name="output",
            as_type="event",
            start_time=event.timestamp,
            output=event.tool_result_summary,
            metadata={
                "agent_name": agent_name,
                **(event.metadata or {}),
            }
        )
        output_event.end()
    
    def flush(self) -> None:
        """Flush any buffered events."""
        if self._client and not self._closed:
            try:
                self._client.flush()
            except Exception as e:
                print(f"LangfuseSink flush error: {e}")
    
    def close(self) -> None:
        """Close the sink and release resources."""
        if not self._closed:
            # Flush before marking closed, so flush() guard passes
            self.flush()
            self._closed = True
            if self._client:
                try:
                    # Close any remaining spans
                    with self._lock:
                        for span in self._spans.values():
                            try:
                                span.end()
                            except Exception:
                                pass
                        self._spans.clear()
                        self._traces.clear()
                except Exception:
                    pass