"""
MiddleGroundBackend - Enhanced Rich + prompt_toolkit UI backend.

The "middle ground" between plain text and full TUI:
- Rich for formatted output (panels, markdown, syntax highlighting)
- prompt_toolkit for advanced input (history, completion, key bindings)
- Streaming markdown with no-flicker approach (stable lines + live window)
- Terminal cleanup on exit/crash

Key design: Uses Aider-style streaming where stable lines go to console
above a small Live window, preserving terminal scrollback.
"""

import sys
import time
import atexit
import signal
from typing import Dict, Any, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import UIConfig

from .events import UIEventType

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.live import Live
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import InMemoryHistory
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


class MarkdownStreamer:
    """Streaming markdown renderer with no-flicker approach.
    
    Splits output into stable lines (printed above) and unstable lines
    (in Live window). This preserves terminal scrollback while allowing
    smooth streaming updates.
    """
    
    def __init__(self, console: 'Console', live_window: int = 6):
        """Initialize streamer.
        
        Args:
            console: Rich Console instance
            live_window: Number of lines to keep in live area
        """
        self._console = console
        self._live_window = live_window
        self._live: Optional[Live] = None
        self._printed_lines: List[str] = []
        self._current_text = ""
        self._min_delay = 1.0 / 20  # 20 FPS max
        self._last_update = 0.0
    
    def start(self) -> None:
        """Start the streaming display."""
        self._live = Live(Text(""), console=self._console, refresh_per_second=20)
        self._live.start()
        self._printed_lines = []
        self._current_text = ""
    
    def update(self, text: str, final: bool = False) -> None:
        """Update the displayed content.
        
        Args:
            text: Full markdown text so far
            final: If True, this is the final update
        """
        if not self._live:
            return
        
        now = time.time()
        if not final and now - self._last_update < self._min_delay:
            return
        self._last_update = now
        
        self._current_text = text
        lines = text.splitlines(keepends=True)
        num_lines = len(lines)
        
        # How many lines are stable (not in live window)?
        stable_count = num_lines - self._live_window if not final else num_lines
        
        if stable_count > len(self._printed_lines):
            # Print new stable lines above live area
            new_lines = lines[len(self._printed_lines):stable_count]
            for line in new_lines:
                self._console.print(line.rstrip('\n'))
            self._printed_lines = lines[:stable_count]
        
        if final:
            self._live.update(Text(""))
            self._live.stop()
            self._live = None
        else:
            # Update live window with remaining lines
            rest = lines[stable_count:]
            rest_text = "".join(rest)
            self._live.update(Text(rest_text))
    
    def stop(self) -> None:
        """Stop the streaming display."""
        if self._live:
            self._live.stop()
            self._live = None


class MiddleGroundBackend:
    """Enhanced Rich + prompt_toolkit UI backend."""
    
    def __init__(self, config: Optional['UIConfig'] = None):
        """Initialize MiddleGroundBackend.
        
        Args:
            config: Optional UIConfig instance
            
        Raises:
            ImportError: If required deps not installed
        """
        if not RICH_AVAILABLE:
            raise ImportError("Rich is required. Install with: pip install rich")
        if not PROMPT_TOOLKIT_AVAILABLE:
            raise ImportError("prompt_toolkit is required. Install with: pip install prompt_toolkit")
        
        self._config = config
        self._current_message = ""
        self._in_stream = False
        
        # Configure console
        no_color = config.no_color if config else False
        self._console = Console(
            force_terminal=True,
            no_color=no_color,
            highlight=not no_color,
        )
        
        # Markdown streamer for no-flicker streaming
        self._streamer: Optional[MarkdownStreamer] = None
        
        # prompt_toolkit session
        self._prompt_session: Optional[PromptSession] = None
        self._history = InMemoryHistory()
        
        # Register cleanup handlers
        self._register_cleanup()
    
    def _register_cleanup(self) -> None:
        """Register terminal cleanup handlers."""
        def cleanup():
            self._cleanup_terminal()
        
        atexit.register(cleanup)
        
        # Handle signals
        def signal_handler(signum, frame):
            self._cleanup_terminal()
            sys.exit(128 + signum)
        
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except (ValueError, OSError):
            # Can't set signal handlers in some contexts
            pass
    
    def _cleanup_terminal(self) -> None:
        """Restore terminal state."""
        try:
            # Stop any active streaming
            if self._streamer:
                self._streamer.stop()
            
            # Restore cursor
            sys.stdout.write("\033[?25h")  # Show cursor
            sys.stdout.write("\033[0m")    # Reset colors
            sys.stdout.flush()
        except Exception:
            pass
    
    def emit(self, event_type: UIEventType, data: Dict[str, Any]) -> None:
        """Emit an event to the UI.
        
        Args:
            event_type: Type of event
            data: Event data payload
        """
        if event_type == UIEventType.MESSAGE_START:
            self._in_stream = True
            self._current_message = ""
            agent_name = data.get('agent_name', '')
            if agent_name:
                self._console.print(f"[bold cyan][{agent_name}][/bold cyan]")
            
            # Start streaming display
            self._streamer = MarkdownStreamer(self._console)
            self._streamer.start()
        
        elif event_type == UIEventType.MESSAGE_CHUNK:
            content = data.get('content', '')
            self._current_message += content
            
            if self._streamer:
                self._streamer.update(self._current_message)
        
        elif event_type == UIEventType.MESSAGE_END:
            self._in_stream = False
            
            if self._streamer:
                self._streamer.update(self._current_message, final=True)
                self._streamer = None
            
            self._current_message = ""
        
        elif event_type == UIEventType.TOOL_START:
            tool_name = data.get('tool_name', 'tool')
            args = data.get('args', '')
            self._console.print(f"\n[dim]▶ {tool_name}[/dim]", end="")
            if args and self._config and self._config.verbose:
                self._console.print(f" [dim]{args}[/dim]")
            else:
                self._console.print()
        
        elif event_type == UIEventType.TOOL_END:
            result = data.get('result', '')
            success = data.get('success', True)
            if result:
                style = "green" if success else "red"
                # Truncate long results
                if len(result) > 200 and not (self._config and self._config.verbose):
                    result = result[:200] + "..."
                self._console.print(f"[{style}]{result}[/{style}]")
        
        elif event_type == UIEventType.ERROR:
            message = data.get('message', 'Unknown error')
            self._console.print(Panel(
                f"[bold red]{message}[/bold red]",
                title="Error",
                border_style="red",
            ))
        
        elif event_type == UIEventType.WARNING:
            message = data.get('message', '')
            self._console.print(f"[yellow]⚠ {message}[/yellow]")
        
        elif event_type == UIEventType.STATUS_UPDATE:
            status = data.get('status', '')
            if status:
                # Use transient status (overwrite with \r)
                sys.stdout.write(f"\r[{status}]")
                sys.stdout.flush()
        
        elif event_type == UIEventType.STATUS_CLEAR:
            sys.stdout.write("\r" + " " * 40 + "\r")
            sys.stdout.flush()
        
        elif event_type == UIEventType.APPROVAL_REQUEST:
            prompt = data.get('prompt', 'Approve?')
            action = data.get('action', '')
            
            self._console.print()
            self._console.print(Panel(
                f"{prompt}\n\n[dim]{action}[/dim]" if action else prompt,
                title="[bold yellow]Approval Required[/bold yellow]",
                border_style="yellow",
            ))
            self._console.print("[bold][y][/bold]es / [bold][n][/bold]o / [bold][a][/bold]lways: ", end="")
    
    def prompt(self, message: str = "") -> str:
        """Get user input with prompt_toolkit.
        
        Args:
            message: Optional prompt message
            
        Returns:
            User input string
        """
        if not self._prompt_session:
            self._prompt_session = PromptSession(
                history=self._history,
                enable_history_search=True,
            )
        
        try:
            return self._prompt_session.prompt(message)
        except EOFError:
            return ""
        except KeyboardInterrupt:
            return ""
    
    async def prompt_async(self, message: str = "") -> str:
        """Get user input asynchronously.
        
        Args:
            message: Optional prompt message
            
        Returns:
            User input string
        """
        if not self._prompt_session:
            self._prompt_session = PromptSession(
                history=self._history,
                enable_history_search=True,
            )
        
        try:
            return await self._prompt_session.prompt_async(message)
        except EOFError:
            return ""
        except KeyboardInterrupt:
            return ""
    
    def is_tty(self) -> bool:
        """Check if running in a TTY.
        
        Returns:
            True if stdout is a TTY
        """
        return sys.stdout.isatty()
    
    def render_markdown(self, text: str) -> None:
        """Render markdown text.
        
        Args:
            text: Markdown text to render
        """
        md = Markdown(text)
        self._console.print(md)
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self._cleanup_terminal()
