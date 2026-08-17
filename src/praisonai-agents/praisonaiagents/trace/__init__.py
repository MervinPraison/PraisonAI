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

from .._lazy import create_lazy_getattr_with_groups

__all__ = [
    # Core types
    "ActionEvent",
    "ActionEventType",
    "ActionTraceConfig",
    # Sink protocols (AGENTS.md naming: XProtocol)
    "TraceSinkProtocol",
    "TraceSink",  # Backward compat alias
    "NoOpSink",
    "ListSink",
    # Emitter
    "TraceEmitter",
    # Redaction
    "redact_dict",
    "REDACT_KEYS",
    # C7 — PII redaction for LLM egress
    "scrub_pii_text",
    "enable_pii_redaction",
    "disable_pii_redaction",
    # Context events (for replay)
    "ContextEvent",
    "ContextEventType",
    "ContextTraceSinkProtocol",
    "ContextTraceSink",  # Backward compat alias
    "ContextNoOpSink",
    "ContextListSink",
    "ContextTraceEmitter",
    # Context manager
    "trace_context",
    # Global emitter registry
    "get_context_emitter",
    "set_context_emitter",
    "reset_context_emitter",
]


_LAZY_GROUPS = {
    'protocol': {
        'ActionEvent': ('praisonaiagents.trace.protocol', 'ActionEvent'),
        'ActionEventType': ('praisonaiagents.trace.protocol', 'ActionEventType'),
        'ActionTraceConfig': ('praisonaiagents.trace.protocol', 'ActionTraceConfig'),
        'TraceSinkProtocol': ('praisonaiagents.trace.protocol', 'TraceSinkProtocol'),
        'TraceSink': ('praisonaiagents.trace.protocol', 'TraceSink'),
        'NoOpSink': ('praisonaiagents.trace.protocol', 'NoOpSink'),
        'ListSink': ('praisonaiagents.trace.protocol', 'ListSink'),
        'TraceEmitter': ('praisonaiagents.trace.protocol', 'TraceEmitter'),
    },
    'redact': {
        'redact_dict': ('praisonaiagents.trace.redact', 'redact_dict'),
        'REDACT_KEYS': ('praisonaiagents.trace.redact', 'REDACT_KEYS'),
        'scrub_pii_text': ('praisonaiagents.trace.redact', 'scrub_pii_text'),
        'enable_pii_redaction': ('praisonaiagents.trace.redact', 'enable_pii_redaction'),
        'disable_pii_redaction': ('praisonaiagents.trace.redact', 'disable_pii_redaction'),
    },
    'context_events': {
        'ContextEvent': ('praisonaiagents.trace.context_events', 'ContextEvent'),
        'ContextEventType': ('praisonaiagents.trace.context_events', 'ContextEventType'),
        'ContextTraceSinkProtocol': ('praisonaiagents.trace.context_events', 'ContextTraceSinkProtocol'),
        'ContextTraceSink': ('praisonaiagents.trace.context_events', 'ContextTraceSink'),
        'ContextNoOpSink': ('praisonaiagents.trace.context_events', 'ContextNoOpSink'),
        'ContextListSink': ('praisonaiagents.trace.context_events', 'ContextListSink'),
        'ContextTraceEmitter': ('praisonaiagents.trace.context_events', 'ContextTraceEmitter'),
        'trace_context': ('praisonaiagents.trace.context_events', 'trace_context'),
        'get_context_emitter': ('praisonaiagents.trace.context_events', 'get_context_emitter'),
        'set_context_emitter': ('praisonaiagents.trace.context_events', 'set_context_emitter'),
        'reset_context_emitter': ('praisonaiagents.trace.context_events', 'reset_context_emitter'),
    },
}

__getattr__ = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)
