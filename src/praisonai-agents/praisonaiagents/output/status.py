"""
Actions Output Mode for PraisonAI Agents.

Provides a filtered output mode that shows only:
1. Agent lifecycle events (start/end)
2. Tool calls (name, args, duration, status)
3. Final agent output

This module integrates with the existing display callback system
and uses the existing redaction utilities.

Usage:
    from praisonaiagents import Agent
    
    # Enable via preset
    agent = Agent(instructions="...", output="actions")
    agent.start("Do something")
    
    # Or via OutputConfig
    from praisonaiagents.config import OutputConfig
    agent = Agent(
        instructions="...",
        output=OutputConfig(actions_trace=True)
    )
"""

import sys
import time
import threading
from datetime import datetime
from typing import Any, Dict, Optional, TextIO

# Global state for actions mode
_status_output_enabled = False
_status_output: Optional['StatusOutput'] = None
_agent_start_times: Dict[str, float] = {}
_output_lock = threading.Lock()  # Multi-agent safe output lock
_ai_call_count = 0  # Track AI call count for context display


def _format_timestamp(ts: float) -> str:
    """Format timestamp as HH:MM:SS.mmm."""
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}"


def _format_duration(duration_ms: Optional[float]) -> str:
    """Format duration in human-readable form."""
    if duration_ms is None:
        return ""
    if duration_ms < 1000:
        return f"{duration_ms:.0f}ms"
    return f"{duration_ms / 1000:.1f}s"


def _truncate(text: str, max_len: int = 50) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


class StatusOutput:
    """
    Sink for actions-only output.
    
    Formats and outputs action events in a clean, readable format.
    Supports both human-readable text and JSONL output.
    
    Thread-safe for multi-agent concurrent execution.
    """
    
    def __init__(
        self,
        file: TextIO = None,
        format: str = "text",  # "text" or "jsonl"
        redact: bool = True,
        use_color: bool = True,
        show_timestamps: bool = True,  # NEW: control timestamp display
        show_metrics: bool = False,  # Enable metrics display for debug mode
    ):
        self._file = file or sys.stderr  # Use stderr to not interfere with agent output
        self._format = format
        self._redact = redact
        self._use_color = use_color
        self._show_timestamps = show_timestamps
        self._show_metrics = show_metrics
        self._console = None
        self._tool_start_times: Dict[str, float] = {}
        self._lock = threading.Lock()  # Per-sink lock for thread safety
    
    def _get_console(self):
        """Get Rich console for colored output."""
        if self._console is None and self._use_color:
            try:
                from rich.console import Console
                self._console = Console(file=self._file, force_terminal=True)
            except ImportError:
                self._console = None
        return self._console
    
    def _redact_args(self, args: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Redact sensitive data from args."""
        if args is None or not self._redact:
            return args
        try:
            from ..trace.redact import redact_dict
            return redact_dict(args)
        except ImportError:
            return args
    
    def _format_args(self, args: Optional[Dict[str, Any]]) -> str:
        """Format tool arguments for display."""
        if not args:
            return ""
        
        redacted = self._redact_args(args)
        parts = []
        for k, v in (redacted or {}).items():
            if isinstance(v, str):
                v_str = f'"{_truncate(v, 30)}"'
            else:
                v_str = _truncate(str(v), 30)
            parts.append(f"{k}={v_str}")
        
        return _truncate(", ".join(parts), 80)
    
    def agent_start(self, agent_name: str) -> None:
        """Record agent start."""
        ts = time.time()
        _agent_start_times[agent_name] = ts
        
        if self._format == "jsonl":
            self._emit_jsonl("agent_start", agent_name=agent_name, timestamp=ts)
        else:
            self._emit_text(f"▶ Agent:{agent_name} started", ts, "green")
    
    def agent_end(self, agent_name: str, duration_ms: Optional[float] = None) -> None:
        """Record agent end."""
        ts = time.time()
        
        # Calculate duration if not provided
        if duration_ms is None and agent_name in _agent_start_times:
            start_ts = _agent_start_times.pop(agent_name, None)
            if start_ts:
                duration_ms = (ts - start_ts) * 1000
        
        duration_str = f" [{_format_duration(duration_ms)}]" if duration_ms else ""
        
        if self._format == "jsonl":
            self._emit_jsonl("agent_end", agent_name=agent_name, timestamp=ts, duration_ms=duration_ms)
        else:
            self._emit_text(f"◀ Agent:{agent_name} completed{duration_str}", ts, "green")
    
    def llm_start(self, model: str = None, agent_name: Optional[str] = None) -> None:
        """Record LLM call start."""
        global _ai_call_count
        ts = time.time()
        self._llm_start_time = ts
        _ai_call_count += 1
        
        # Context based on call sequence
        if _ai_call_count == 1:
            context = "thinking"
        else:
            context = "responding"
        
        if self._format == "jsonl":
            self._emit_jsonl("llm_start", model=model, agent_name=agent_name, timestamp=ts)
        else:
            self._emit_text(f"▸ AI → {context}...", ts, "yellow")
    
    def llm_end(
        self, 
        duration_ms: Optional[float] = None, 
        agent_name: Optional[str] = None,
        model: Optional[str] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: Optional[float] = None,
        latency_ms: Optional[float] = None,
    ) -> None:
        """Record LLM call end with optional metrics for debug mode."""
        ts = time.time()
        
        # Use latency_ms if provided, otherwise calculate from start time
        if latency_ms is not None:
            duration_ms = latency_ms
        elif duration_ms is None and hasattr(self, '_llm_start_time'):
            start_ts = self._llm_start_time
            if start_ts:
                duration_ms = (ts - start_ts) * 1000
        
        # Track session totals for summary
        if not hasattr(self, '_session_tokens_in'):
            self._session_tokens_in = 0
            self._session_tokens_out = 0
            self._session_cost = 0.0
            self._session_llm_calls = 0
        
        self._session_tokens_in += tokens_in
        self._session_tokens_out += tokens_out
        if cost:
            self._session_cost += cost
        self._session_llm_calls += 1
        
        # Only show metrics line in debug mode (when show_metrics is enabled)
        show_metrics = getattr(self, '_show_metrics', False)
        
        if self._format == "jsonl":
            self._emit_jsonl("llm_end", agent_name=agent_name, timestamp=ts, 
                           duration_ms=duration_ms, model=model, 
                           tokens_in=tokens_in, tokens_out=tokens_out, cost=cost)
        elif show_metrics and (tokens_in > 0 or tokens_out > 0):
            # Debug mode: show metrics line
            duration_str = f" [{_format_duration(duration_ms)}]" if duration_ms else ""
            model_str = model.split('/')[-1] if model else "?"  # Short model name
            cost_str = f" (~${cost:.4f})" if cost else ""
            
            metrics_line = f"  │ 📊 {model_str}: {tokens_in}→{tokens_out} tokens{cost_str}{duration_str}"
            self._emit_text(metrics_line, ts, "dim", show_timestamp=False)
    
    def tool_start(self, tool_name: str, tool_args: Optional[Dict[str, Any]] = None, agent_name: Optional[str] = None) -> None:
        """Record tool start - stores info for inline display with result."""
        ts = time.time()
        self._tool_start_times[tool_name] = ts
        self._pending_tool_args = tool_args  # Store for display with result
        self._pending_tool_name = tool_name
        
        # Don't emit anything here - wait for result to show inline
    
    def tool_end(
        self,
        tool_name: str,
        duration_ms: Optional[float] = None,
        status: str = "ok",
        result_summary: Optional[str] = None,
        agent_name: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Record tool end with inline display showing tool call and result."""
        ts = time.time()
        
        # Calculate duration if not provided
        if duration_ms is None and tool_name in self._tool_start_times:
            start_ts = self._tool_start_times.pop(tool_name, None)
            if start_ts:
                duration_ms = (ts - start_ts) * 1000
        
        if self._format == "jsonl":
            self._emit_jsonl(
                "tool_end",
                tool_name=tool_name,
                duration_ms=duration_ms,
                status=status,
                result_summary=_truncate(result_summary, 200) if result_summary else None,
                agent_name=agent_name,
                error_message=error_message,
                timestamp=ts,
            )
        else:
            # Build inline tool call with result: │ → tool(args) → result
            args_str = ""
            if hasattr(self, '_pending_tool_args') and self._pending_tool_args:
                args_str = self._format_args(self._pending_tool_args)
            
            result_str = ""
            if result_summary:
                result_str = f" → {_truncate(result_summary, 50)}"
            elif error_message:
                result_str = f" → ✗ {_truncate(error_message, 50)}"
            
            color = "cyan" if status == "ok" else "red"
            self._emit_text(f"  │ → {tool_name}({args_str}){result_str}", ts, color)
    
    def output(self, content: str, agent_name: Optional[str] = None) -> None:
        """Record final output."""
        ts = time.time()
        
        if self._format == "jsonl":
            self._emit_jsonl("output", content=_truncate(content, 500), agent_name=agent_name, timestamp=ts)
        else:
            separator = "─" * 50
            self._emit_text(separator, ts, "dim", show_timestamp=False)
            self._emit_text("Final Output:", ts, "bold", show_timestamp=False)
            # Print actual content without truncation for final output
            with self._lock:  # Thread-safe output
                print(content, file=self._file)
    
    def _emit_text(self, message: str, ts: float, style: str = None, show_timestamp: bool = True) -> None:
        """Emit a text line. Thread-safe for multi-agent execution."""
        # Respect both instance-level and per-call timestamp settings
        should_show_ts = show_timestamp and self._show_timestamps
        ts_str = f"[{_format_timestamp(ts)}] " if should_show_ts else ""
        
        with self._lock:  # Thread-safe output
            console = self._get_console()
            if console and self._use_color:
                if style:
                    console.print(f"[dim]{ts_str}[/dim][{style}]{message}[/{style}]")
                else:
                    console.print(f"[dim]{ts_str}[/dim]{message}")
            else:
                print(f"{ts_str}{message}", file=self._file)
    
    def _emit_jsonl(self, event_type: str, **kwargs) -> None:
        """Emit a JSONL line. Thread-safe for multi-agent execution."""
        import json
        data = {"event": event_type, **{k: v for k, v in kwargs.items() if v is not None}}
        with self._lock:  # Thread-safe output
            print(json.dumps(data, default=str), file=self._file)


def enable_status_output(
    file: TextIO = None,
    format: str = "text",
    redact: bool = True,
    use_color: bool = True,
    show_timestamps: bool = True,
    show_metrics: bool = False,  # Enable metrics for debug mode
) -> StatusOutput:
    """
    Enable actions output mode globally.
    
    This registers callbacks with the display system to capture
    tool calls and agent lifecycle events.
    
    Args:
        file: Output file (default: stderr)
        format: Output format ("text" or "jsonl")
        redact: Whether to redact sensitive data (default: True)
        use_color: Whether to use colored output (default: True)
        show_timestamps: Whether to show timestamps (default: True)
        show_metrics: Whether to show token/cost metrics (default: False)
    
    Returns:
        StatusOutput instance for programmatic access
    """
    global _status_output_enabled, _status_output, _ai_call_count
    
    # Reset AI call counter for new agent run
    _ai_call_count = 0
    
    _status_output = StatusOutput(
        file=file,
        format=format,
        redact=redact,
        use_color=use_color,
        show_timestamps=show_timestamps,
        show_metrics=show_metrics,
    )
    _status_output_enabled = True
    
    # Register callbacks with the display system
    from ..main import register_display_callback
    
    def on_tool_call(message: str = None, tool_name: str = None, tool_input: dict = None, tool_output: str = None, **kwargs):
        """Callback for tool calls."""
        if not _status_output_enabled or _status_output is None:
            return
        
        if tool_name:
            # Emit tool_start when we see a tool call
            _status_output.tool_start(tool_name, tool_input)
            # Emit tool_end immediately since we have the output
            if tool_output is not None:
                _status_output.tool_end(
                    tool_name,
                    status="ok",
                    result_summary=str(tool_output)[:200] if tool_output else None,
                )
    
    def on_interaction(message: str = None, response: str = None, agent_name: str = None, generation_time: float = None, **kwargs):
        """Callback for agent interactions (final output)."""
        if not _status_output_enabled or _status_output is None:
            return
        
        # Only emit output for final responses
        if response:
            _status_output.output(response, agent_name)
    
    def on_error(message: str = None, **kwargs):
        """Callback for errors."""
        if not _status_output_enabled or _status_output is None:
            return
        
        if message:
            ts = time.time()
            _status_output._emit_text(f"✗ Error: {message}", ts, "red")
    
    def on_llm_start(model: str = None, agent_name: str = None, **kwargs):
        """Callback for LLM calls."""
        if not _status_output_enabled or _status_output is None:
            return
        
        _status_output.llm_start(model=model, agent_name=agent_name)
    
    def on_llm_end(model: str = None, tokens_in: int = 0, tokens_out: int = 0, cost: float = None, latency_ms: float = None, **kwargs):
        """Callback for LLM call completion with metrics."""
        if not _status_output_enabled or _status_output is None:
            return
        
        _status_output.llm_end(model=model, tokens_in=tokens_in, tokens_out=tokens_out, cost=cost, latency_ms=latency_ms)
    
    # Register the callbacks
    register_display_callback('tool_call', on_tool_call)
    register_display_callback('interaction', on_interaction)
    register_display_callback('error', on_error)
    register_display_callback('llm_start', on_llm_start)
    register_display_callback('llm_end', on_llm_end)
    
    return _status_output


def disable_status_output() -> None:
    """Disable actions output mode."""
    global _status_output_enabled, _status_output
    _status_output_enabled = False
    _status_output = None


def is_status_output_enabled() -> bool:
    """Check if actions mode is enabled."""
    return _status_output_enabled


def get_status_output() -> Optional[StatusOutput]:
    """Get the current actions sink."""
    return _status_output


__all__ = [
    "StatusOutput",
    "enable_status_output",
    "disable_status_output",
    "is_status_output_enabled",
    "get_status_output",
]
