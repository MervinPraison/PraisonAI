"""
Composer Widget for PraisonAI TUI.

Input area for composing messages with slash command support.
"""

from typing import Callable, List, Optional
import asyncio

try:
    from textual.widget import Widget
    from textual.widgets import TextArea, Input
    from textual.containers import Horizontal, Vertical
    from textual.message import Message
    from textual.binding import Binding
    from textual import events
    from rich.text import Text
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Widget = object
    Message = object


if TEXTUAL_AVAILABLE:
    class ComposerWidget(Vertical):
        """
        Input composer for chat messages.
        
        Features:
        - Multi-line input
        - Slash command detection
        - @ mention support
        - History navigation
        - Send on Enter or Ctrl+Enter
        """
        
        BINDINGS = [
            Binding("enter", "submit", "Send", show=True),
            Binding("escape", "cancel", "Cancel", show=False),
            Binding("up", "history_prev", "Previous", show=False),
            Binding("down", "history_next", "Next", show=False),
        ]
        
        DEFAULT_CSS = """
        ComposerWidget {
            height: auto;
            max-height: 10;
            border: solid $primary;
            background: $surface;
            padding: 0 1;
        }
        
        ComposerWidget TextArea {
            height: auto;
            min-height: 3;
            max-height: 8;
        }
        
        ComposerWidget .hint {
            color: $text-muted;
            text-style: italic;
        }
        """
        
        class Submitted(Message):
            """Event when message is submitted."""
            def __init__(self, content: str, is_command: bool = False):
                self.content = content
                self.is_command = is_command
                super().__init__()
        
        class CommandDetected(Message):
            """Event when a slash command is detected."""
            def __init__(self, command: str, args: str):
                self.command = command
                self.args = args
                super().__init__()
        
        def __init__(
            self,
            placeholder: str = "Type your message... (Enter to send, Shift+Enter for newline, /help for commands)",
            multiline: bool = True,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._placeholder = placeholder
            self._multiline = multiline
            self._history: List[str] = []
            self._history_index = -1
            self._current_input = ""
            self._is_processing = False
        
        def compose(self):
            """Compose the widget."""
            yield TextArea(
                "",
                id="composer-input",
                language=None,
            )
        
        def on_mount(self) -> None:
            """Handle mount event."""
            text_area = self.query_one("#composer-input", TextArea)
            text_area.focus()
        
        async def on_text_area_changed(self, event: TextArea.Changed) -> None:
            """Handle text changes."""
            content = event.text_area.text
            
            # Detect slash commands
            if content.startswith("/"):
                parts = content[1:].split(maxsplit=1)
                if parts:
                    command = parts[0]
                    args = parts[1] if len(parts) > 1 else ""
                    self.post_message(self.CommandDetected(command, args))
        
        def on_key(self, event: events.Key) -> None:
            """Handle key events."""
            # Shift+Enter inserts newline
            if event.key == "shift+enter":
                text_area = self.query_one("#composer-input", TextArea)
                text_area.insert("\n")
                event.prevent_default()
                return
            
            # Enter sends the message (unless processing)
            if event.key == "enter":
                event.prevent_default()
                self.action_submit()
        
        def action_submit(self) -> None:
            """Submit the current input.
            
            Note: We allow submitting even while processing to enable
            queueing multiple messages.
            """
            text_area = self.query_one("#composer-input", TextArea)
            content = text_area.text.strip()
            
            if not content:
                return
            
            # Add to history
            if content and (not self._history or self._history[-1] != content):
                self._history.append(content)
            self._history_index = -1
            
            # Check if it's a command
            is_command = content.startswith("/")
            
            # Clear input
            text_area.clear()
            
            # Emit event
            self.post_message(self.Submitted(content, is_command))
        
        def action_cancel(self) -> None:
            """Cancel current input."""
            text_area = self.query_one("#composer-input", TextArea)
            text_area.clear()
            self._history_index = -1
        
        def action_history_prev(self) -> None:
            """Navigate to previous history item."""
            if not self._history:
                return
            
            text_area = self.query_one("#composer-input", TextArea)
            
            if self._history_index == -1:
                self._current_input = text_area.text
                self._history_index = len(self._history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
            
            text_area.clear()
            text_area.insert(self._history[self._history_index])
        
        def action_history_next(self) -> None:
            """Navigate to next history item."""
            if self._history_index == -1:
                return
            
            text_area = self.query_one("#composer-input", TextArea)
            
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                text_area.clear()
                text_area.insert(self._history[self._history_index])
            else:
                self._history_index = -1
                text_area.clear()
                text_area.insert(self._current_input)
        
        def set_processing(self, processing: bool) -> None:
            """Set processing state.
            
            Note: We no longer disable the text area during processing
            to allow users to queue additional messages while waiting.
            """
            self._is_processing = processing
        
        @property
        def text(self) -> str:
            """Get current text."""
            text_area = self.query_one("#composer-input", TextArea)
            return text_area.text
        
        @text.setter
        def text(self, value: str) -> None:
            """Set current text."""
            text_area = self.query_one("#composer-input", TextArea)
            text_area.clear()
            text_area.insert(value)
        
        def focus_input(self) -> None:
            """Focus the input area."""
            text_area = self.query_one("#composer-input", TextArea)
            text_area.focus()

else:
    class ComposerWidget:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
