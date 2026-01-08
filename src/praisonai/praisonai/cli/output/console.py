"""
Central Output Controller for PraisonAI CLI.

Provides unified output handling with multiple modes:
- text: Rich formatted output (default)
- json: Single JSON object output
- stream-json: NDJSON streaming events
- screen-reader: Plain text, no spinners/panels
- quiet: Minimal output
- verbose: Debug details
"""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

# Lazy import Rich to avoid startup overhead
_console = None
_rich_available = None


def _get_rich_available() -> bool:
    """Check if Rich is available."""
    global _rich_available
    if _rich_available is None:
        try:
            import importlib.util
            _rich_available = importlib.util.find_spec("rich") is not None
        except ImportError:
            _rich_available = False
    return _rich_available


def _get_console():
    """Get or create Rich Console instance."""
    global _console
    if _console is None and _get_rich_available():
        from rich.console import Console
        _console = Console()
    return _console


class OutputMode(str, Enum):
    """Output mode enumeration."""
    TEXT = "text"
    JSON = "json"
    STREAM_JSON = "stream-json"
    SCREEN_READER = "screen-reader"
    QUIET = "quiet"
    VERBOSE = "verbose"


@dataclass
class StreamEvent:
    """Event for stream-json output."""
    event_type: str  # start, progress, result, error
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    run_id: Optional[str] = None
    trace_id: Optional[str] = None
    agent_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "event": self.event_type,
            "timestamp": self.timestamp,
        }
        if self.run_id:
            result["run_id"] = self.run_id
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.agent_id:
            result["agent_id"] = self.agent_id
        if self.data:
            result["data"] = self.data
        if self.message:
            result["message"] = self.message
        return result
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class OutputController:
    """
    Central output controller for CLI commands.
    
    Handles all output formatting based on the selected mode.
    Thread-safe and supports context managers.
    """
    
    def __init__(
        self,
        mode: OutputMode = OutputMode.TEXT,
        no_color: bool = False,
        run_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ):
        self.mode = mode
        self.no_color = no_color or os.environ.get("NO_COLOR", "").lower() in ("1", "true", "yes")
        self.run_id = run_id
        self.trace_id = trace_id
        self._events: List[StreamEvent] = []
        self._console = None
    
    @property
    def console(self):
        """Get Rich console (lazy loaded)."""
        if self._console is None:
            self._console = _get_console()
        return self._console
    
    @property
    def is_json_mode(self) -> bool:
        """Check if in any JSON output mode."""
        return self.mode in (OutputMode.JSON, OutputMode.STREAM_JSON)
    
    @property
    def is_quiet(self) -> bool:
        """Check if in quiet mode."""
        return self.mode == OutputMode.QUIET
    
    @property
    def is_verbose(self) -> bool:
        """Check if in verbose mode."""
        return self.mode == OutputMode.VERBOSE
    
    @property
    def is_screen_reader(self) -> bool:
        """Check if in screen reader mode."""
        return self.mode == OutputMode.SCREEN_READER
    
    def print(self, message: str, style: Optional[str] = None, **kwargs) -> None:
        """Print a message respecting the current mode."""
        if self.is_quiet:
            return
        
        if self.is_json_mode:
            # In JSON mode, collect messages but don't print directly
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            # Plain text output
            print(message)
        else:
            # Rich formatted output
            if self.console:
                self.console.print(message, style=style, **kwargs)
            else:
                print(message)
    
    def print_error(self, message: str, code: Optional[str] = None, remediation: Optional[str] = None) -> None:
        """Print an error message with optional remediation."""
        if self.is_json_mode:
            error_data = {
                "error": True,
                "message": message,
            }
            if code:
                error_data["code"] = code
            if remediation:
                error_data["remediation"] = remediation
            if self.run_id:
                error_data["run_id"] = self.run_id
            if self.trace_id:
                error_data["trace_id"] = self.trace_id
            print(json.dumps(error_data), file=sys.stderr)
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            print(f"ERROR: {message}", file=sys.stderr)
            if remediation:
                print(f"FIX: {remediation}", file=sys.stderr)
        else:
            from rich.panel import Panel
            from rich.text import Text
            
            content = Text()
            content.append(f"❌ {message}\n", style="bold red")
            if remediation:
                content.append(f"\n💡 Fix: {remediation}", style="yellow")
            
            if self.console:
                self.console.print(Panel(content, title="Error", border_style="red"))
            else:
                print(f"ERROR: {message}", file=sys.stderr)
    
    def print_success(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Print a success message."""
        if self.is_json_mode:
            success_data = {
                "success": True,
                "message": message,
            }
            if data:
                success_data.update(data)
            if self.run_id:
                success_data["run_id"] = self.run_id
            if self.trace_id:
                success_data["trace_id"] = self.trace_id
            print(json.dumps(success_data, default=str))
            return
        
        if self.is_quiet:
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            print(f"SUCCESS: {message}")
        else:
            self.print(f"✅ {message}", style="bold green")
    
    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        if self.is_json_mode or self.is_quiet:
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            print(f"WARNING: {message}")
        else:
            self.print(f"⚠️  {message}", style="bold yellow")
    
    def print_info(self, message: str) -> None:
        """Print an info message."""
        if self.is_json_mode or self.is_quiet:
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            print(f"INFO: {message}")
        else:
            self.print(f"ℹ️  {message}", style="bold blue")
    
    def print_debug(self, message: str) -> None:
        """Print a debug message (only in verbose mode)."""
        if not self.is_verbose:
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            print(f"DEBUG: {message}")
        else:
            self.print(f"🔍 {message}", style="dim")
    
    def emit_event(self, event_type: str, message: Optional[str] = None, data: Optional[Dict[str, Any]] = None, agent_id: Optional[str] = None) -> None:
        """Emit a stream event (for stream-json mode)."""
        event = StreamEvent(
            event_type=event_type,
            run_id=self.run_id,
            trace_id=self.trace_id,
            agent_id=agent_id,
            message=message,
            data=data or {},
        )
        self._events.append(event)
        
        if self.mode == OutputMode.STREAM_JSON:
            print(event.to_json(), flush=True)
    
    def emit_start(self, message: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit a start event."""
        self.emit_event("start", message=message, data=data)
    
    def emit_progress(self, message: Optional[str] = None, data: Optional[Dict[str, Any]] = None, agent_id: Optional[str] = None) -> None:
        """Emit a progress event."""
        self.emit_event("progress", message=message, data=data, agent_id=agent_id)
    
    def emit_result(self, message: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit a result event."""
        self.emit_event("result", message=message, data=data)
    
    def emit_error(self, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Emit an error event."""
        self.emit_event("error", message=message, data=data)
    
    def print_json(self, data: Any) -> None:
        """Print JSON data."""
        print(json.dumps(data, indent=2, default=str))
    
    def print_table(self, headers: List[str], rows: List[List[Any]], title: Optional[str] = None) -> None:
        """Print a table."""
        if self.is_json_mode:
            table_data = [dict(zip(headers, row)) for row in rows]
            print(json.dumps(table_data, default=str))
            return
        
        if self.is_quiet:
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            # Plain text table
            if title:
                print(f"\n{title}")
                print("-" * len(title))
            
            # Calculate column widths
            widths = [len(h) for h in headers]
            for row in rows:
                for i, cell in enumerate(row):
                    widths[i] = max(widths[i], len(str(cell)))
            
            # Print header
            header_line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
            print(header_line)
            print("-" * len(header_line))
            
            # Print rows
            for row in rows:
                print(" | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
        else:
            from rich.table import Table
            
            table = Table(title=title)
            for header in headers:
                table.add_column(header)
            for row in rows:
                table.add_row(*[str(cell) for cell in row])
            
            if self.console:
                self.console.print(table)
    
    def print_panel(self, content: str, title: Optional[str] = None, style: str = "cyan") -> None:
        """Print a panel."""
        if self.is_json_mode or self.is_quiet:
            return
        
        if self.is_screen_reader or self.no_color or not _get_rich_available():
            if title:
                print(f"\n=== {title} ===")
            print(content)
            if title:
                print("=" * (len(title) + 8))
        else:
            from rich.panel import Panel
            
            if self.console:
                self.console.print(Panel(content, title=title, border_style=style))
    
    def get_events(self) -> List[Dict[str, Any]]:
        """Get all collected events."""
        return [e.to_dict() for e in self._events]


# Global output controller instance
_output_controller: Optional[OutputController] = None


def get_output_controller() -> OutputController:
    """Get the global output controller."""
    global _output_controller
    if _output_controller is None:
        _output_controller = OutputController()
    return _output_controller


def set_output_controller(controller: OutputController) -> None:
    """Set the global output controller."""
    global _output_controller
    _output_controller = controller
