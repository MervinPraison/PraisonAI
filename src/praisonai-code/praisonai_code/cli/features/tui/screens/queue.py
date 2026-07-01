"""
Queue Screen for PraisonAI TUI.

Queue management interface.
"""

from typing import Optional, List

try:
    from textual.screen import Screen
    from textual.containers import Vertical, Horizontal
    from textual.widgets import Static, Footer, DataTable, Button
    from textual.binding import Binding
    from textual.message import Message
    from rich.text import Text
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Screen = object
    Message = object


if TEXTUAL_AVAILABLE:
    class QueueScreen(Screen):
        """
        Queue management screen.
        
        Displays full queue with management options.
        """
        
        BINDINGS = [
            Binding("escape", "back", "Back", show=True),
            Binding("c", "cancel", "Cancel", show=True),
            Binding("r", "retry", "Retry", show=True),
            Binding("x", "clear", "Clear Queue", show=True),
            Binding("enter", "select", "Select", show=False),
        ]
        
        DEFAULT_CSS = """
        QueueScreen {
            background: $surface;
        }
        
        QueueScreen #queue-header {
            height: 3;
            background: $primary;
            padding: 1;
        }
        
        QueueScreen DataTable {
            height: 1fr;
        }
        
        QueueScreen #queue-actions {
            height: 3;
            padding: 1;
        }
        """
        
        class RunCancelled(Message):
            def __init__(self, run_id: str):
                self.run_id = run_id
                super().__init__()
        
        class RunRetried(Message):
            def __init__(self, run_id: str):
                self.run_id = run_id
                super().__init__()
        
        class QueueCleared(Message):
            pass
        
        def __init__(
            self,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._selected_run_id: Optional[str] = None
        
        def compose(self):
            """Compose the screen."""
            yield Static("Queue Management", id="queue-header")
            yield DataTable(id="queue-table")
            with Horizontal(id="queue-actions"):
                yield Button("Cancel [C]", id="btn-cancel", variant="error")
                yield Button("Retry [R]", id="btn-retry", variant="warning")
                yield Button("Clear [X]", id="btn-clear", variant="default")
                yield Button("Back [Esc]", id="btn-back", variant="primary")
            yield Footer()
        
        def on_mount(self) -> None:
            """Handle mount."""
            table = self.query_one("#queue-table", DataTable)
            table.add_columns(
                "ID", "Agent", "Input", "State", "Priority", 
                "Wait Time", "Duration"
            )
            table.cursor_type = "row"
        
        def update_runs(self, runs: List[dict]) -> None:
            """Update the runs display."""
            table = self.query_one("#queue-table", DataTable)
            table.clear()
            
            for run in runs:
                state = run.get("state", "unknown")
                state_style = {
                    "queued": "yellow",
                    "running": "green",
                    "succeeded": "cyan",
                    "failed": "red",
                    "cancelled": "dim",
                }.get(state, "")
                
                state_text = Text(state, style=state_style)
                
                input_preview = run.get("input", "")[:40]
                if len(run.get("input", "")) > 40:
                    input_preview += "..."
                
                table.add_row(
                    run.get("run_id", "")[:8],
                    run.get("agent_name", ""),
                    input_preview,
                    state_text,
                    run.get("priority", "normal"),
                    run.get("wait_time", "-"),
                    run.get("duration", "-"),
                    key=run.get("run_id"),
                )
        
        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            """Handle row selection."""
            if event.row_key:
                self._selected_run_id = str(event.row_key.value)
        
        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle button press."""
            if event.button.id == "btn-cancel":
                self.action_cancel()
            elif event.button.id == "btn-retry":
                self.action_retry()
            elif event.button.id == "btn-clear":
                self.action_clear()
            elif event.button.id == "btn-back":
                self.action_back()
        
        def action_back(self) -> None:
            """Go back to main screen."""
            self.app.pop_screen()
        
        def action_cancel(self) -> None:
            """Cancel selected run."""
            if self._selected_run_id:
                self.post_message(self.RunCancelled(self._selected_run_id))
        
        def action_retry(self) -> None:
            """Retry selected run."""
            if self._selected_run_id:
                self.post_message(self.RunRetried(self._selected_run_id))
        
        def action_clear(self) -> None:
            """Clear the queue."""
            self.post_message(self.QueueCleared())

else:
    class QueueScreen:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
