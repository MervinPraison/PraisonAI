"""
Queue Panel Widget for PraisonAI TUI.

Displays queue status and allows queue management.
"""

from typing import List, Optional
from dataclasses import dataclass

try:
    from textual.widget import Widget
    from textual.widgets import Static, DataTable, Button
    from textual.containers import Vertical
    from textual.reactive import reactive
    from textual.message import Message
    from rich.text import Text
    from rich.panel import Panel
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Widget = object
    Message = object


@dataclass
class QueueItem:
    """A queue item for display."""
    run_id: str
    agent_name: str
    input_preview: str
    state: str
    priority: str
    wait_time: str


if TEXTUAL_AVAILABLE:
    class QueuePanelWidget(Vertical):
        """
        Queue panel widget.
        
        Displays:
        - Queue summary (queued/running counts)
        - List of queued runs
        - Cancel/retry buttons
        """
        
        DEFAULT_CSS = """
        QueuePanelWidget {
            height: 100%;
            border: solid $secondary;
            background: $surface;
            padding: 0 1;
        }
        
        QueuePanelWidget .queue-header {
            height: 1;
            background: $secondary;
            padding: 0 1;
        }
        
        QueuePanelWidget DataTable {
            height: 1fr;
        }
        
        QueuePanelWidget .queue-item-queued {
            color: $warning;
        }
        
        QueuePanelWidget .queue-item-running {
            color: $success;
        }
        
        QueuePanelWidget .queue-item-failed {
            color: $error;
        }
        """
        
        class RunSelected(Message):
            """Event when a run is selected."""
            def __init__(self, run_id: str):
                self.run_id = run_id
                super().__init__()
        
        class CancelRequested(Message):
            """Event when cancel is requested."""
            def __init__(self, run_id: str):
                self.run_id = run_id
                super().__init__()
        
        class RetryRequested(Message):
            """Event when retry is requested."""
            def __init__(self, run_id: str):
                self.run_id = run_id
                super().__init__()
        
        class DeleteRequested(Message):
            """Event when delete is requested."""
            def __init__(self, run_id: str):
                self.run_id = run_id
                super().__init__()
        
        class EditRequested(Message):
            """Event when edit is requested."""
            def __init__(self, run_id: str, new_content: str):
                self.run_id = run_id
                self.new_content = new_content
                super().__init__()
        
        queued_count: reactive[int] = reactive(0)
        running_count: reactive[int] = reactive(0)
        
        def __init__(
            self,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._items: List[QueueItem] = []
            self._selected_run_id: Optional[str] = None
        
        def compose(self):
            """Compose the widget."""
            yield Static("Queue", id="queue-title", classes="queue-header")
            yield DataTable(id="queue-table")
        
        def on_mount(self) -> None:
            """Handle mount."""
            table = self.query_one("#queue-table", DataTable)
            table.add_columns("ID", "Agent", "Input", "State", "Priority")
            table.cursor_type = "row"
            self._update_header()
        
        def watch_queued_count(self, value: int) -> None:
            self._update_header()
        
        def watch_running_count(self, value: int) -> None:
            self._update_header()
        
        def _update_header(self) -> None:
            """Update the header text."""
            try:
                header = self.query_one("#queue-title", Static)
                text = Text()
                text.append("Queue ", style="bold")
                text.append(f"⏳ {self.queued_count} queued", style="yellow")
                text.append(" │ ", style="dim")
                text.append(f"▶ {self.running_count} running", style="green")
                header.update(text)
            except Exception:
                pass
        
        def update_items(self, items: List[QueueItem]) -> None:
            """Update the queue items."""
            self._items = items
            
            table = self.query_one("#queue-table", DataTable)
            table.clear()
            
            for item in items:
                # Style based on state
                state_style = {
                    "queued": "yellow",
                    "running": "green",
                    "failed": "red",
                    "cancelled": "dim",
                    "succeeded": "cyan",
                }.get(item.state.lower(), "")
                
                state_text = Text(item.state, style=state_style)
                
                # Truncate input preview
                input_preview = item.input_preview[:30]
                if len(item.input_preview) > 30:
                    input_preview += "..."
                
                table.add_row(
                    item.run_id[:8],
                    item.agent_name,
                    input_preview,
                    state_text,
                    item.priority,
                    key=item.run_id,
                )
        
        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            """Handle row selection."""
            if event.row_key:
                self._selected_run_id = str(event.row_key.value)
                self.post_message(self.RunSelected(self._selected_run_id))
        
        def cancel_selected(self) -> None:
            """Cancel the selected run."""
            if self._selected_run_id:
                self.post_message(self.CancelRequested(self._selected_run_id))
        
        def retry_selected(self) -> None:
            """Retry the selected run."""
            if self._selected_run_id:
                self.post_message(self.RetryRequested(self._selected_run_id))
        
        def delete_selected(self) -> None:
            """Delete the selected run."""
            if self._selected_run_id:
                self.post_message(self.DeleteRequested(self._selected_run_id))
        
        def edit_selected(self, new_content: str) -> None:
            """Edit the selected run's input content."""
            if self._selected_run_id:
                self.post_message(self.EditRequested(self._selected_run_id, new_content))
        
        @property
        def selected_run_id(self) -> Optional[str]:
            """Get the selected run ID."""
            return self._selected_run_id

else:
    class QueuePanelWidget:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
