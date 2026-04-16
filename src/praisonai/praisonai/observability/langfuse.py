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
from praisonaiagents.trace.context_events import ContextEvent, ContextEventType, ContextTraceSinkProtocol


class _ContextToActionBridge:
    """
    Bridge adapter that implements ContextTraceSinkProtocol and forwards
    ContextEvents to ActionEvents for LangfuseSink.
    
    This enables LangfuseSink to receive events from ContextTraceEmitter,
    which captures the rich lifecycle events that actual agents emit.
    """
    
    __slots__ = ("_action_sink",)
    
    def __init__(self, action_sink: "LangfuseSink") -> None:
        self._action_sink = action_sink
    
    def emit(self, event: ContextEvent) -> None:
        """Convert ContextEvent to ActionEvent and forward to action sink."""
        action_event = self._convert_context_to_action(event)
        if action_event:
            self._action_sink.emit(action_event)
    
    def flush(self) -> None:
        """Forward flush to action sink."""
        self._action_sink.flush()
    
    def close(self) -> None:
        """Forward close to action sink."""
        self._action_sink.close()
    
    def _convert_context_to_action(self, ctx_event: ContextEvent) -> Optional[ActionEvent]:
        """Convert ContextEvent to ActionEvent format."""
        # Map ContextEventType to ActionEventType
        event_type_mapping = {
            ContextEventType.AGENT_START: ActionEventType.AGENT_START,
            ContextEventType.AGENT_END: ActionEventType.AGENT_END,
            ContextEventType.TOOL_CALL_START: ActionEventType.TOOL_START,
            ContextEventType.TOOL_CALL_END: ActionEventType.TOOL_END,
            ContextEventType.LLM_REQUEST: None,  # No direct ActionEvent equivalent
            ContextEventType.LLM_RESPONSE: None,  # No direct ActionEvent equivalent
            ContextEventType.MESSAGE_ADDED: None,  # No direct ActionEvent equivalent
            ContextEventType.SESSION_START: None,  # No direct ActionEvent equivalent
            ContextEventType.SESSION_END: None,  # No direct ActionEvent equivalent
        }
        
        action_type = event_type_mapping.get(ctx_event.event_type)
        if not action_type:
            return None

        tool_result_summary = (
            ctx_event.data.get("tool_result_summary")
            if isinstance(ctx_event.data, dict)
            else None
        )
        if tool_result_summary is None and isinstance(ctx_event.data, dict):
            tool_result_summary = ctx_event.data.get("result")

        status = ctx_event.data.get("status") if isinstance(ctx_event.data, dict) else None
        error_message = ctx_event.data.get("error_message") if isinstance(ctx_event.data, dict) else None
        if error_message is None and isinstance(ctx_event.data, dict):
            error_message = ctx_event.data.get("error")
        if status is None and action_type == ActionEventType.TOOL_END:
            status = "error" if error_message else "completed"
        
        # Convert to ActionEvent format
        return ActionEvent(
            event_type=action_type.value,
            timestamp=ctx_event.timestamp,
            agent_id=ctx_event.session_id,
            agent_name=ctx_event.agent_name or "unknown",
            tool_name=ctx_event.data.get("tool_name"),
            tool_args=ctx_event.data.get("tool_args"),
            tool_result_summary=tool_result_summary,
            duration_ms=ctx_event.data.get("duration_ms", 0.0),
            status=status,
            error_message=error_message,
            metadata=ctx_event.data,
        )


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
    
    __slots__ = ("_config", "_client", "_traces", "_spans", "_lock", "_closed", "_metadata")
    
    def __init__(self, config: Optional[LangfuseSinkConfig] = None, metadata: Optional[Dict[str, Any]] = None):
        self._config = config or LangfuseSinkConfig()
        self._client: Optional[Any] = None  # Lazy-loaded langfuse.Langfuse
        self._traces: Dict[str, Any] = {}  # agent_name -> trace observation
        self._metadata = metadata or {}  # Additional metadata for traces
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
        
        # Merge flow correlation metadata with agent metadata
        agent_metadata = {
            "agent_id": event.agent_id,
            "agent_name": agent_name,
            "schema_version": event.schema_version,
            **(event.metadata if event.metadata else {}),
            **self._metadata  # Include flow correlation metadata
        }
        
        span = self._client.start_observation(
            name=trace_name,
            as_type="span",
            input=trace_input,
            metadata=agent_metadata,
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
        
        # Merge flow correlation metadata with tool metadata
        tool_metadata = {
            "tool_name": tool_name,
            "agent_name": agent_name,
            "tool_invocation_id": tool_invocation_id,
            **(event.metadata if event.metadata else {}),
            **self._metadata  # Include flow correlation metadata
        }
        
        tool_span = self._client.start_observation(
            name=tool_name,
            as_type="span",
            input=event.tool_args,
            metadata=tool_metadata,
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
        
        # Include flow correlation metadata in error events
        error_metadata = {
            "agent_name": agent_name,
            "error_type": type(event.error_message).__name__ if hasattr(event.error_message, '__class__') else "str",
            **(event.metadata if event.metadata else {}),
            **self._metadata  # Include flow correlation metadata
        }
        
        error_event = self._client.start_observation(
            name="error",
            as_type="event",
            level="ERROR",
            status_message=event.error_message,
            input=event.tool_args,
            metadata=error_metadata,
        )
        error_event.end()
    
    def _handle_output(self, event: ActionEvent, agent_name: str) -> None:
        """Handle OUTPUT -> create output event observation."""
        # Include flow correlation metadata in output events
        output_metadata = {
            "agent_name": agent_name,
            "output_type": "agent_output",
            **(event.metadata if event.metadata else {}),
            **self._metadata  # Include flow correlation metadata
        }
        
        output_event = self._client.start_observation(
            name="output",
            as_type="event",
            output=event.tool_result_summary,
            metadata=output_metadata,
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
    
    def context_sink(self) -> ContextTraceSinkProtocol:
        """
        Get a ContextTraceSinkProtocol bridge that forwards ContextEvents to this sink.
        
        This enables LangfuseSink to receive events from ContextTraceEmitter,
        which captures the rich lifecycle events that actual agents emit
        (agent_start, agent_end, tool_call_start, tool_call_end, llm_request, llm_response).
        
        Returns:
            ContextTraceSinkProtocol: Bridge that converts and forwards events
        """
        return _ContextToActionBridge(self)
