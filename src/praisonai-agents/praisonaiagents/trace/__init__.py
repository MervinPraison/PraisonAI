"""
Trace Module for PraisonAI Agents.

Provides lightweight action tracing for the `output="actions"` mode.
Shows agent lifecycle events, tool calls, and final output without
verbose internal details.

Zero Performance Impact:
- All imports are lazy loaded via __getattr__
- NoOpSink is the default (zero overhead when not used)
- Disabled emitter has near-zero overhead

Usage:
    from praisonaiagents import Agent
    
    # Simple usage - shows action trace
    agent = Agent(instructions="...", output="actions")
    agent.start("Do something")
    
    # Advanced - capture to file
    from praisonaiagents.trace import ActionTraceConfig
    
    agent = Agent(
        instructions="...",
        output="actions",
        trace=ActionTraceConfig(
            sink_type="jsonl",
            file_path="trace.jsonl",
        )
    )
"""

__all__ = [
    # Core types
    "ActionEvent",
    "ActionEventType",
    "ActionTraceConfig",
    # Sinks
    "TraceSink",
    "NoOpSink",
    "ListSink",
    # Emitter
    "TraceEmitter",
    # Redaction
    "redact_dict",
    "REDACT_KEYS",
    # Context events (for replay)
    "ContextEvent",
    "ContextEventType",
    "ContextTraceSink",
    "ContextNoOpSink",
    "ContextListSink",
    "ContextTraceEmitter",
]


def __getattr__(name: str):
    """Lazy load module components to avoid import overhead."""
    if name in ("ActionEvent", "ActionEventType", "ActionTraceConfig"):
        from .protocol import ActionEvent, ActionEventType, ActionTraceConfig
        return locals()[name]
    
    if name in ("TraceSink", "NoOpSink", "ListSink"):
        from .protocol import TraceSink, NoOpSink, ListSink
        return locals()[name]
    
    if name == "TraceEmitter":
        from .protocol import TraceEmitter
        return TraceEmitter
    
    if name in ("redact_dict", "REDACT_KEYS"):
        from .redact import redact_dict, REDACT_KEYS
        return locals()[name]
    
    # Context events (for replay)
    if name in ("ContextEvent", "ContextEventType"):
        from .context_events import ContextEvent, ContextEventType
        return locals()[name]
    
    if name in ("ContextTraceSink", "ContextNoOpSink", "ContextListSink"):
        from .context_events import ContextTraceSink, ContextNoOpSink, ContextListSink
        return locals()[name]
    
    if name == "ContextTraceEmitter":
        from .context_events import ContextTraceEmitter
        return ContextTraceEmitter
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
