"""
Status Output Mode for PraisonAI Agents.

Provides a clean, simple output mode that shows:
1. LLM call status (calling, completed)
2. Tool execution status (name, duration, result)
3. Final response (no boxes, just text)

This is ideal for:
- CLI users who want minimal but informative output
- External apps that parse status updates
- Logging and monitoring

Usage:
    from praisonaiagents import Agent
    
    # Enable via preset
    agent = Agent(instructions="...", output="status")
    agent.start("Do something")
    
    # Output:
    # [13:45:02] Calling LLM (gpt-4o-mini)...
    # [13:45:03] Executing tool: get_weather
    # [13:45:03] Tool completed (0.1s)
    # Response: The weather in Paris is sunny.
"""

import sys
import time
import threading
from datetime import datetime
from typing import Any, Dict, Optional, TextIO

# Global state for status mode
_trace_output_enabled = False
_trace_output: Optional['TraceOutput'] = None
_output_lock = threading.Lock()  # Multi-agent safe output lock


def _format_timestamp() -> str:
    """Format current time as HH:MM:SS."""
    return datetime.now().strftime("%H:%M:%S")


class TraceOutput:
    """
    Sink for clean status output.
    
    Formats and outputs status events in a simple, readable format.
    No boxes, no panels, just timestamped status lines.
    
    Thread-safe for multi-agent concurrent execution.
    """
    
    def __init__(
        self,
        file: TextIO = None,
        use_color: bool = True,
        show_timestamps: bool = True,
        use_markdown: bool = True,
    ):
        self._file = file or sys.stderr
        self._use_color = use_color
        self._show_timestamps = show_timestamps
        self._use_markdown = use_markdown
        self._console = None
        self._lock = threading.Lock()
        self._tool_start_times: Dict[str, float] = {}
        self._llm_start_time: Optional[float] = None
    
    def _get_console(self):
        """Get Rich console for colored output."""
        if self._console is None and self._use_color:
            try:
                from rich.console import Console
                self._console = Console(file=self._file, force_terminal=True)
            except ImportError:
                self._console = None
        return self._console
    
    def _emit(self, message: str, style: str = None) -> None:
        """Emit a status line. Thread-safe."""
        ts_str = f"[{_format_timestamp()}] " if self._show_timestamps else ""
        
        with self._lock:
            console = self._get_console()
            if console and self._use_color:
                if style:
                    console.print(f"[dim]{ts_str}[/dim][{style}]{message}[/{style}]")
                else:
                    console.print(f"[dim]{ts_str}[/dim]{message}")
            else:
                print(f"{ts_str}{message}", file=self._file)
    
    def llm_start(self, model: str = None) -> None:
        """Record LLM call start."""
        self._llm_start_time = time.time()
        model_str = f" ({model})" if model else ""
        self._emit(f"Calling LLM{model_str}...", "cyan")
    
    def llm_end(
        self, 
        duration_ms: float = None,
        model: str = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: float = None,
    ) -> None:
        """Record LLM call end with optional metrics."""
        # If duration_ms was passed and is positive, use it directly
        # Otherwise calculate from internal tracking
        if duration_ms is not None and duration_ms > 0:
            pass  # Use the passed value
        elif self._llm_start_time:
            duration_ms = (time.time() - self._llm_start_time) * 1000
        
        duration_str = f" [{duration_ms/1000:.1f}s]" if duration_ms and duration_ms > 0 else ""
        
        # Show metrics if tokens are available
        if tokens_in > 0 or tokens_out > 0:
            model_str = model.split('/')[-1] if model else "?"
            cost_str = f" (~${cost:.4f})" if cost and cost > 0 else ""
            metrics_line = f"  │ 📊 {model_str}: {tokens_in}→{tokens_out} tokens{cost_str}{duration_str}"
            self._emit(metrics_line, "dim")
        else:
            self._emit(f"LLM responded{duration_str}", "green")
        self._llm_start_time = None
    
    def tool_start(self, tool_name: str, tool_args: Dict[str, Any] = None) -> None:
        """Record tool execution start."""
        self._tool_start_times[tool_name] = time.time()
        
        # Format args compactly
        args_str = ""
        if tool_args:
            parts = []
            for k, v in tool_args.items():
                v_str = str(v)
                if len(v_str) > 30:
                    v_str = v_str[:27] + "..."
                parts.append(f"{k}={repr(v_str) if isinstance(v, str) else v_str}")
            args_str = f"({', '.join(parts)})"
        
        self._emit(f"▸ {tool_name}{args_str}", "blue")
    
    def tool_end(
        self,
        tool_name: str,
        duration_ms: float = None,
        result: str = None,
        success: bool = True,
    ) -> None:
        """Record tool execution end."""
        # Calculate duration if not provided
        if duration_ms is None and tool_name in self._tool_start_times:
            start_ts = self._tool_start_times.pop(tool_name, None)
            if start_ts:
                duration_ms = (time.time() - start_ts) * 1000
        
        duration_str = f" [{duration_ms/1000:.1f}s]" if duration_ms else ""
        status_icon = "✓" if success else "✗"
        
        # Show result inline if short
        result_str = ""
        if result:
            result_preview = str(result)
            if len(result_preview) > 50:
                result_preview = result_preview[:47] + "..."
            result_str = f" → {result_preview}"
        
        color = "green" if success else "red"
        self._emit(f"  └─ {tool_name}{result_str}{duration_str} {status_icon}", color)
    
    def response(self, content: str, agent_name: str = None) -> None:
        """Output final response with optional Markdown rendering."""
        with self._lock:
            console = self._get_console()
            
            # Separator line
            if console and self._use_color:
                console.print("")
                console.print("[bold]Response:[/bold]")
                
                # Render as Markdown if enabled
                if self._use_markdown:
                    try:
                        from rich.markdown import Markdown
                        console.print(Markdown(content))
                    except ImportError:
                        # Fallback if markdown-it not available
                        console.print(content)
                else:
                    console.print(content)
            else:
                print("", file=self._file)
                print("Response:", file=self._file)
                print(content, file=self._file)
    
    def error(self, message: str) -> None:
        """Output error message."""
        self._emit(f"✗ Error: {message}", "red")


def enable_trace_output(
    file: TextIO = None,
    use_color: bool = True,
    show_timestamps: bool = True,
    use_markdown: bool = True,
) -> TraceOutput:
    """
    Enable status output mode globally.
    
    This registers callbacks with the display system to capture
    tool calls and output clean status updates.
    
    Args:
        file: Output file (default: stderr)
        use_color: Whether to use colored output (default: True)
        show_timestamps: Whether to show timestamps (default: True)
        use_markdown: Whether to render response as Markdown (default: True)
    
    Returns:
        TraceOutput instance
    """
    global _trace_output_enabled, _trace_output
    
    _trace_output = TraceOutput(
        file=file,
        use_color=use_color,
        show_timestamps=show_timestamps,
        use_markdown=use_markdown,
    )
    _trace_output_enabled = True
    
    # Register callbacks with the display system
    from ..main import register_display_callback
    
    def on_tool_call(
        message: str = None,
        tool_name: str = None,
        tool_input: dict = None,
        tool_output: str = None,
        **kwargs
    ):
        """Callback for tool calls."""
        if not _trace_output_enabled or _trace_output is None:
            return
        
        # Handle structured tool call (when tool_name is set)
        if tool_name:
            _trace_output.tool_start(tool_name, tool_input)
            # If we have output, call tool_end immediately for inline display
            if tool_output is not None:
                _trace_output.tool_end(tool_name, result=str(tool_output)[:200], success=True)
            return
        
        # Handle legacy message format (for backward compatibility)
        if message:
            # Check for "Function X returned: Y" pattern
            if "returned:" in message.lower():
                import re
                match = re.match(r'Function (\w+) returned: (.+)', message, re.IGNORECASE)
                if match:
                    func_name = match.group(1)
                    result = match.group(2).strip('"')
                    _trace_output.tool_end(func_name, result=result, success=True)
            # "Calling function" message is already shown via tool_start, skip
    
    def on_interaction(
        message: str = None,
        response: str = None,
        agent_name: str = None,
        generation_time: float = None,
        **kwargs
    ):
        """Callback for agent interactions (final output)."""
        if not _trace_output_enabled or _trace_output is None:
            return
        
        # Output final response
        if response:
            _trace_output.response(response, agent_name)
    
    def on_error(message: str = None, **kwargs):
        """Callback for errors."""
        if not _trace_output_enabled or _trace_output is None:
            return
        
        if message:
            _trace_output.error(message)
    
    def on_llm_start(model: str = None, agent_name: str = None, **kwargs):
        """Callback for LLM call start."""
        if not _trace_output_enabled or _trace_output is None:
            return
        
        _trace_output.llm_start(model=model)
    
    def on_llm_end(model: str = None, tokens_in: int = 0, tokens_out: int = 0, cost: float = None, latency_ms: float = None, **kwargs):
        """Callback for LLM call completion with optional metrics."""
        if not _trace_output_enabled or _trace_output is None:
            return
        
        _trace_output.llm_end(
            duration_ms=latency_ms, 
            model=model, 
            tokens_in=tokens_in, 
            tokens_out=tokens_out, 
            cost=cost
        )
    
    # Register the callbacks
    register_display_callback('tool_call', on_tool_call)
    register_display_callback('interaction', on_interaction)
    register_display_callback('error', on_error)
    register_display_callback('llm_start', on_llm_start)
    register_display_callback('llm_end', on_llm_end)
    
    return _trace_output


def disable_trace_output() -> None:
    """Disable status output mode."""
    global _trace_output_enabled, _trace_output
    _trace_output_enabled = False
    _trace_output = None


def is_trace_output_enabled() -> bool:
    """Check if status mode is enabled."""
    return _trace_output_enabled


def get_trace_output() -> Optional[TraceOutput]:
    """Get the current status sink."""
    return _trace_output


__all__ = [
    "TraceOutput",
    "enable_trace_output",
    "disable_trace_output",
    "is_trace_output_enabled",
    "get_trace_output",
]
