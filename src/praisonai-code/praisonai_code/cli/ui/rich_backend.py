"""
RichBackend - Rich-based UI backend.

Uses Rich library for formatted terminal output with colors,
panels, markdown rendering, and syntax highlighting.
"""

import sys
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import UIConfig

from .events import UIEventType

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class RichBackend:
    """Rich-based UI backend with formatted output."""
    
    def __init__(self, config: Optional['UIConfig'] = None):
        """Initialize RichBackend.
        
        Args:
            config: Optional UIConfig instance
            
        Raises:
            ImportError: If rich is not installed
        """
        if not RICH_AVAILABLE:
            raise ImportError("Rich is required for RichBackend. Install with: pip install rich")
        
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
                self._console.print(f"[bold cyan][{agent_name}][/bold cyan] ", end="")
        
        elif event_type == UIEventType.MESSAGE_CHUNK:
            content = data.get('content', '')
            # For streaming, use raw print to avoid Rich overhead
            sys.stdout.write(content)
            sys.stdout.flush()
            self._current_message += content
        
        elif event_type == UIEventType.MESSAGE_END:
            self._in_stream = False
            if not self._current_message.endswith('\n'):
                sys.stdout.write('\n')
                sys.stdout.flush()
            self._current_message = ""
        
        elif event_type == UIEventType.TOOL_START:
            tool_name = data.get('tool_name', 'tool')
            self._console.print(f"\n[dim]▶ {tool_name}[/dim]")
        
        elif event_type == UIEventType.TOOL_END:
            result = data.get('result', '')
            success = data.get('success', True)
            if result:
                style = "green" if success else "red"
                self._console.print(f"[{style}]{result}[/{style}]")
        
        elif event_type == UIEventType.ERROR:
            message = data.get('message', 'Unknown error')
            self._console.print(f"[bold red]Error:[/bold red] {message}")
        
        elif event_type == UIEventType.WARNING:
            message = data.get('message', '')
            self._console.print(f"[yellow]Warning:[/yellow] {message}")
        
        elif event_type == UIEventType.STATUS_UPDATE:
            status = data.get('status', '')
            if status and self._config and self._config.verbose:
                self._console.print(f"[dim][{status}][/dim]")
        
        elif event_type == UIEventType.APPROVAL_REQUEST:
            prompt = data.get('prompt', 'Approve?')
            self._console.print(Panel(
                prompt,
                title="[bold yellow]Approval Required[/bold yellow]",
                border_style="yellow",
            ))
            self._console.print("[y]es / [n]o / [a]lways: ", end="")
    
    def prompt(self, message: str = "") -> str:
        """Get user input.
        
        Args:
            message: Optional prompt message
            
        Returns:
            User input string
        """
        if message:
            self._console.print(message, end="")
        
        try:
            return input()
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
        return self.prompt(message)
    
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
        pass
