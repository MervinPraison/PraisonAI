"""
Chat Widget for PraisonAI TUI.

Displays chat history with streaming support.
"""

from typing import List, Optional
from dataclasses import dataclass, field
import time

try:
    from textual.widget import Widget
    from textual.widgets import Static
    from textual.containers import VerticalScroll
    from textual.message import Message
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.text import Text
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Widget = object
    Message = object


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    run_id: Optional[str] = None
    agent_name: Optional[str] = None
    is_streaming: bool = False
    
    @property
    def display_role(self) -> str:
        """Get display name for role."""
        if self.role == "user":
            return "You"
        elif self.role == "assistant":
            return self.agent_name or "Assistant"
        elif self.role == "system":
            return "System"
        elif self.role == "tool":
            return "Tool"
        return self.role.title()


if TEXTUAL_AVAILABLE:
    class ChatWidget(VerticalScroll):
        """
        Widget for displaying chat history with scrollbar.
        
        Uses VerticalScroll for proper scrollbar support.
        Messages are mounted directly to this container.
        """
        
        DEFAULT_CSS = """
        ChatWidget {
            height: 1fr;
            border: solid $primary;
            background: $surface;
            padding: 0 1;
            overflow-y: auto;
        }
        
        ChatWidget .message-user {
            background: $primary-darken-2;
            margin: 1 0;
            padding: 1;
        }
        
        ChatWidget .message-assistant {
            background: $surface-darken-1;
            margin: 1 0;
            padding: 1;
        }
        
        ChatWidget .message-system {
            background: $warning-darken-3;
            margin: 1 0;
            padding: 1;
            color: $text-muted;
        }
        
        ChatWidget .message-streaming {
            border: dashed $accent;
        }
        """
        
        class MessageAdded(Message):
            """Event when a message is added."""
            def __init__(self, message: ChatMessage):
                self.message = message
                super().__init__()
        
        class StreamingUpdate(Message):
            """Event when streaming content updates."""
            def __init__(self, run_id: str, content: str):
                self.run_id = run_id
                self.content = content
                super().__init__()
        
        def __init__(
            self,
            max_messages: int = 1000,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._messages: List[ChatMessage] = []
            self._max_messages = max_messages
            self._streaming_widgets: dict = {}
        
        def compose(self):
            """Compose the widget - no inner container needed."""
            # Messages are mounted directly to this VerticalScroll
            # Must yield from empty iterable (not return None)
            yield from ()
        
        async def add_message(self, message: ChatMessage) -> None:
            """Add a message to the chat.
            
            NEW BEHAVIOR: Messages render NEWEST at TOP.
            This guarantees visibility without relying on scroll.
            """
            self._messages.append(message)
            
            # Trim old messages if needed
            if len(self._messages) > self._max_messages:
                self._messages = self._messages[-self._max_messages:]
            
            # Render message and scroll to show it
            await self._render_message(message)
            
            self.post_message(self.MessageAdded(message))
        
        async def _render_message(self, message: ChatMessage) -> None:
            """Render a message and scroll to show it."""
            # Create role label
            role_style = {
                "user": "bold cyan",
                "assistant": "bold green",
                "system": "bold yellow",
                "tool": "bold magenta",
            }.get(message.role, "bold")
            
            role_text = Text(f"{message.display_role}:", style=role_style)
            
            # Create content
            try:
                content = Markdown(message.content) if message.content else Text("")
            except Exception:
                content = Text(message.content)
            
            # Create panel
            css_class = f"message-{message.role}"
            if message.is_streaming:
                css_class += " message-streaming"
            
            widget_id = f"msg-{message.run_id or id(message)}"
            
            panel = Static(
                Panel(content, title=str(role_text), border_style=role_style),
                id=widget_id,
                classes=css_class,
            )
            
            # Mount directly to this VerticalScroll container
            await self.mount(panel)
            
            # Scroll to end to show new message
            self.scroll_end(animate=False)
            
            if message.is_streaming:
                self._streaming_widgets[message.run_id] = widget_id
        
        async def update_streaming(self, run_id: str, content: str) -> None:
            """Update a streaming message."""
            if run_id not in self._streaming_widgets:
                return
            
            widget_id = self._streaming_widgets[run_id]
            
            try:
                widget = self.query_one(f"#{widget_id}", Static)
                
                # Find the message
                for msg in self._messages:
                    if msg.run_id == run_id:
                        msg.content = content
                        break
                
                # Update content
                try:
                    rendered = Markdown(content + " ▌")
                except Exception:
                    rendered = Text(content + " ▌")
                
                widget.update(Panel(rendered, title="Assistant", border_style="bold green"))
                
                # Scroll to end to keep streaming content visible
                self.scroll_end(animate=False)
                
            except Exception:
                pass
        
        async def complete_streaming(self, run_id: str, final_content: str) -> None:
            """Complete a streaming message."""
            if run_id not in self._streaming_widgets:
                return
            
            widget_id = self._streaming_widgets.pop(run_id)
            
            try:
                widget = self.query_one(f"#{widget_id}", Static)
                
                # Update message
                for msg in self._messages:
                    if msg.run_id == run_id:
                        msg.content = final_content
                        msg.is_streaming = False
                        break
                
                # Update content without cursor
                try:
                    rendered = Markdown(final_content)
                except Exception:
                    rendered = Text(final_content)
                
                widget.update(Panel(rendered, title="Assistant", border_style="bold green"))
                widget.remove_class("message-streaming")
                
            except Exception:
                pass
        
        async def clear(self) -> None:
            """Clear all messages."""
            self._messages.clear()
            self._streaming_widgets.clear()
            
            # Remove all children from this container
            await self.remove_children()
        
        @property
        def messages(self) -> List[ChatMessage]:
            """Get all messages."""
            return self._messages.copy()
        
        @property
        def message_count(self) -> int:
            """Get message count."""
            return len(self._messages)

else:
    class ChatWidget:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
