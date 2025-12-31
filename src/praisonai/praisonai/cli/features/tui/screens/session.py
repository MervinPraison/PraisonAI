"""
Session Screen for PraisonAI TUI.

Session browser and management.
"""

from typing import Optional, List

try:
    from textual.screen import Screen
    from textual.containers import Vertical
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
    class SessionScreen(Screen):
        """
        Session browser screen.
        
        Displays recent sessions and allows resuming.
        """
        
        BINDINGS = [
            Binding("escape", "back", "Back", show=True),
            Binding("enter", "resume", "Resume", show=True),
            Binding("d", "delete", "Delete", show=True),
        ]
        
        DEFAULT_CSS = """
        SessionScreen {
            background: $surface;
        }
        
        SessionScreen #session-header {
            height: 3;
            background: $primary;
            padding: 1;
        }
        
        SessionScreen DataTable {
            height: 1fr;
        }
        """
        
        class SessionSelected(Message):
            def __init__(self, session_id: str):
                self.session_id = session_id
                super().__init__()
        
        class SessionDeleted(Message):
            def __init__(self, session_id: str):
                self.session_id = session_id
                super().__init__()
        
        def __init__(
            self,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._selected_session_id: Optional[str] = None
        
        def compose(self):
            """Compose the screen."""
            yield Static("Sessions", id="session-header")
            yield DataTable(id="session-table")
            yield Footer()
        
        def on_mount(self) -> None:
            """Handle mount."""
            table = self.query_one("#session-table", DataTable)
            table.add_columns("ID", "Created", "Updated", "Runs")
            table.cursor_type = "row"
        
        def update_sessions(self, sessions: List[dict]) -> None:
            """Update the sessions display."""
            table = self.query_one("#session-table", DataTable)
            table.clear()
            
            for session in sessions:
                table.add_row(
                    session.get("session_id", "")[:8],
                    session.get("created_at", "-"),
                    session.get("updated_at", "-"),
                    str(session.get("run_count", 0)),
                    key=session.get("session_id"),
                )
        
        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            """Handle row selection."""
            if event.row_key:
                self._selected_session_id = str(event.row_key.value)
        
        def action_back(self) -> None:
            """Go back."""
            self.app.pop_screen()
        
        def action_resume(self) -> None:
            """Resume selected session."""
            if self._selected_session_id:
                self.post_message(self.SessionSelected(self._selected_session_id))
                self.app.pop_screen()
        
        def action_delete(self) -> None:
            """Delete selected session."""
            if self._selected_session_id:
                self.post_message(self.SessionDeleted(self._selected_session_id))

else:
    class SessionScreen:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
