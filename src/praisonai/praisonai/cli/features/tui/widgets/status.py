"""
Status Widget for PraisonAI TUI.

Displays status bar with session info, model, tokens, and cost.
"""

from typing import Optional
from dataclasses import dataclass

try:
    from textual.widget import Widget
    from textual.widgets import Static
    from textual.containers import Horizontal
    from textual.reactive import reactive
    from rich.text import Text
    from rich.table import Table
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Widget = object


@dataclass
class StatusInfo:
    """Status information."""
    session_id: str = ""
    model: str = "gpt-4o-mini"
    total_tokens: int = 0
    total_cost: float = 0.0
    queued_count: int = 0
    running_count: int = 0
    is_processing: bool = False
    status_message: str = ""


if TEXTUAL_AVAILABLE:
    class StatusWidget(Static):
        """
        Status bar widget.
        
        Displays:
        - Session ID
        - Current model
        - Token usage
        - Cost
        - Queue status
        - Processing indicator
        """
        
        DEFAULT_CSS = """
        StatusWidget {
            height: 1;
            background: $primary;
            color: $text;
            padding: 0 1;
        }
        """
        
        session_id: reactive[str] = reactive("")
        model: reactive[str] = reactive("gpt-4o-mini")
        total_tokens: reactive[int] = reactive(0)
        total_cost: reactive[float] = reactive(0.0)
        queued_count: reactive[int] = reactive(0)
        running_count: reactive[int] = reactive(0)
        is_processing: reactive[bool] = reactive(False)
        status_message: reactive[str] = reactive("")
        
        def __init__(
            self,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__("", name=name, id=id, classes=classes)
        
        def on_mount(self) -> None:
            """Handle mount."""
            self._update_display()
        
        def watch_session_id(self, value: str) -> None:
            self._update_display()
        
        def watch_model(self, value: str) -> None:
            self._update_display()
        
        def watch_total_tokens(self, value: int) -> None:
            self._update_display()
        
        def watch_total_cost(self, value: float) -> None:
            self._update_display()
        
        def watch_queued_count(self, value: int) -> None:
            self._update_display()
        
        def watch_running_count(self, value: int) -> None:
            self._update_display()
        
        def watch_is_processing(self, value: bool) -> None:
            self._update_display()
        
        def watch_status_message(self, value: str) -> None:
            self._update_display()
        
        def _update_display(self) -> None:
            """Update the status display."""
            parts = []
            
            # App name
            parts.append(("◉ PraisonAI", "bold cyan"))
            
            # Session
            if self.session_id:
                parts.append((f"Session: {self.session_id[:8]}", ""))
            
            # Model
            parts.append((f"Model: {self.model}", ""))
            
            # Tokens
            if self.total_tokens > 0:
                parts.append((f"Tokens: {self.total_tokens:,}", ""))
            
            # Cost
            if self.total_cost > 0:
                parts.append((f"${self.total_cost:.4f}", "green"))
            
            # Queue status
            if self.queued_count > 0 or self.running_count > 0:
                queue_text = f"⏳ {self.queued_count} queued"
                if self.running_count > 0:
                    queue_text += f" │ ▶ {self.running_count} running"
                parts.append((queue_text, "yellow"))
            
            # Processing indicator
            if self.is_processing:
                parts.append(("⟳ Processing...", "bold magenta"))
            
            # Status message
            if self.status_message:
                parts.append((self.status_message, "italic"))
            
            # Build text
            text = Text()
            for i, (content, style) in enumerate(parts):
                if i > 0:
                    text.append(" │ ", style="dim")
                text.append(content, style=style)
            
            self.update(text)
        
        def update_info(self, info: StatusInfo) -> None:
            """Update all status info at once."""
            self.session_id = info.session_id
            self.model = info.model
            self.total_tokens = info.total_tokens
            self.total_cost = info.total_cost
            self.queued_count = info.queued_count
            self.running_count = info.running_count
            self.is_processing = info.is_processing
            self.status_message = info.status_message

else:
    class StatusWidget:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
