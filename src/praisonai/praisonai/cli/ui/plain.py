"""
PlainBackend - Zero-dependency UI backend.

Works in any environment: non-TTY, piped output, dumb terminals.
No colors, no formatting, just plain text output.
"""

import sys
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import UIConfig

from .events import UIEventType


class PlainBackend:
    """Plain text UI backend with no dependencies."""
    
    def __init__(self, config: Optional['UIConfig'] = None):
        """Initialize PlainBackend.
        
        Args:
            config: Optional UIConfig instance
        """
        self._config = config
        self._current_message = ""
        self._in_stream = False
    
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
                sys.stdout.write(f"[{agent_name}] ")
                sys.stdout.flush()
        
        elif event_type == UIEventType.MESSAGE_CHUNK:
            content = data.get('content', '')
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
            sys.stdout.write(f"\n[Tool: {tool_name}]\n")
            sys.stdout.flush()
        
        elif event_type == UIEventType.TOOL_END:
            result = data.get('result', '')
            if result:
                sys.stdout.write(f"{result}\n")
                sys.stdout.flush()
        
        elif event_type == UIEventType.ERROR:
            message = data.get('message', 'Unknown error')
            sys.stderr.write(f"Error: {message}\n")
            sys.stderr.flush()
        
        elif event_type == UIEventType.WARNING:
            message = data.get('message', '')
            sys.stderr.write(f"Warning: {message}\n")
            sys.stderr.flush()
        
        elif event_type == UIEventType.STATUS_UPDATE:
            status = data.get('status', '')
            if status and self._config and self._config.verbose:
                sys.stderr.write(f"[{status}]\n")
                sys.stderr.flush()
        
        elif event_type == UIEventType.APPROVAL_REQUEST:
            prompt = data.get('prompt', 'Approve?')
            sys.stdout.write(f"\n{prompt} [y/n]: ")
            sys.stdout.flush()
    
    def prompt(self, message: str = "") -> str:
        """Get user input.
        
        Args:
            message: Optional prompt message
            
        Returns:
            User input string
        """
        if message:
            sys.stdout.write(message)
            sys.stdout.flush()
        
        try:
            return input()
        except EOFError:
            return ""
        except KeyboardInterrupt:
            return ""
    
    async def prompt_async(self, message: str = "") -> str:
        """Get user input asynchronously.
        
        For PlainBackend, this is just a sync call wrapped.
        
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
    
    def cleanup(self) -> None:
        """Cleanup resources. No-op for PlainBackend."""
        pass
