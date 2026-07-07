"""
PraisonAI Streaming Module.

Provides the StreamEvent protocol for pass-through streaming from LLM providers.

This module is lazily loaded to ensure zero performance impact when streaming
features are not used.

Usage:
    from praisonaiagents.streaming import (
        StreamEvent,
        StreamEventType,
        StreamMetrics,
        StreamEventEmitter,
        create_text_printer_callback,
    )
"""

__all__ = [
    "StreamEvent",
    "StreamEventType", 
    "StreamMetrics",
    "StreamEventEmitter",
    "StreamCallback",
    "AsyncStreamCallback",
    "create_text_printer_callback",
    "create_metrics_callback",
    "emit_tool_progress",
    "tool_progress_channel",
    "StreamLogger",
    "create_logging_callback",
    "ProgressLine",
    "merge_progress_line",
    "render_progress",
]


def __getattr__(name: str):
    """Lazy loading of streaming components."""
    if name in __all__:
        # Events module exports
        if name in (
            "StreamEvent", "StreamEventType", "StreamMetrics", 
            "StreamEventEmitter", "StreamCallback", "AsyncStreamCallback",
            "create_text_printer_callback", "create_metrics_callback",
            "emit_tool_progress", "tool_progress_channel"
        ):
            from .events import (
                StreamEvent,
                StreamEventType,
                StreamMetrics,
                StreamEventEmitter,
                StreamCallback,
                AsyncStreamCallback,
                create_text_printer_callback,
                create_metrics_callback,
                emit_tool_progress,
                tool_progress_channel,
            )
            
            _events_exports = {
                "StreamEvent": StreamEvent,
                "StreamEventType": StreamEventType,
                "StreamMetrics": StreamMetrics,
                "StreamEventEmitter": StreamEventEmitter,
                "StreamCallback": StreamCallback,
                "AsyncStreamCallback": AsyncStreamCallback,
                "create_text_printer_callback": create_text_printer_callback,
                "create_metrics_callback": create_metrics_callback,
                "emit_tool_progress": emit_tool_progress,
                "tool_progress_channel": tool_progress_channel,
            }
            return _events_exports.get(name)
        
        # Progress compositor exports
        if name in ("ProgressLine", "merge_progress_line", "render_progress"):
            from .progress import ProgressLine, merge_progress_line, render_progress

            _progress_exports = {
                "ProgressLine": ProgressLine,
                "merge_progress_line": merge_progress_line,
                "render_progress": render_progress,
            }
            return _progress_exports.get(name)

        # Logging module exports
        if name in ("StreamLogger", "create_logging_callback"):
            from .logging import StreamLogger, create_logging_callback
            
            _logging_exports = {
                "StreamLogger": StreamLogger,
                "create_logging_callback": create_logging_callback,
            }
            return _logging_exports.get(name)
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
