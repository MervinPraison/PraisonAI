"""
File Autocomplete Popup Widget for PraisonAI TUI.

Shows file/directory suggestions when user types @.
Reuses FileSearchService from at_mentions.py.
"""

from typing import List, Optional
from dataclasses import dataclass
import os

try:
    from textual.widget import Widget
    from textual.widgets import Static, Input, OptionList
    from textual.widgets.option_list import Option
    from textual.containers import Container
    from textual.reactive import reactive
    from textual.message import Message
    from textual import events
    from rich.text import Text
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Widget = object
    Message = object


@dataclass
class FileInfo:
    """Information about a file for display."""
    path: str
    file_type: str  # "file" or "directory"
    score: int = 100
    
    @property
    def icon(self) -> str:
        """Get icon for file type."""
        return "📁 " if self.file_type == "directory" else "📄 "
    
    @property
    def display(self) -> str:
        """Get display string."""
        return f"{self.icon}{self.path}"


if TEXTUAL_AVAILABLE:
    # Import FileSearchService from at_mentions
    try:
        from ..at_mentions import FileSearchService, detect_at_mention
        FILE_SEARCH_AVAILABLE = True
    except ImportError:
        FILE_SEARCH_AVAILABLE = False
        FileSearchService = None

    class FilePopupWidget(Container):
        """
        Popup widget for file autocomplete.
        
        Features:
        - Shows files/directories matching query
        - Fuzzy search
        - Keyboard navigation
        - Supports ~/ and absolute paths
        """
        
        DEFAULT_CSS = """
        FilePopupWidget {
            layer: popup;
            width: 60;
            height: auto;
            max-height: 15;
            background: $surface;
            border: solid $accent;
            padding: 1;
            margin: 0 0 0 2;
        }
        
        FilePopupWidget #file-popup-title {
            height: 1;
            background: $accent;
            color: $text;
            text-align: center;
            margin-bottom: 1;
        }
        
        FilePopupWidget #file-popup-list {
            height: auto;
            max-height: 10;
            background: $surface-darken-1;
        }
        
        FilePopupWidget #file-popup-hint {
            height: 1;
            color: $text-muted;
            text-align: center;
            margin-top: 1;
        }
        """
        
        class FileSelected(Message):
            """Event when a file is selected."""
            def __init__(self, path: str, at_pos: int):
                self.path = path
                self.at_pos = at_pos
                super().__init__()
        
        class Dismissed(Message):
            """Event when popup is dismissed."""
            pass
        
        # Reactive properties
        filter_text: reactive[str] = reactive("")
        
        def __init__(
            self,
            root_dir: Optional[str] = None,
            at_pos: int = 0,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._root_dir = root_dir or os.getcwd()
            self._at_pos = at_pos
            self._files: List[FileInfo] = []
            self._file_service = None
            if FILE_SEARCH_AVAILABLE and FileSearchService:
                self._file_service = FileSearchService(self._root_dir)
        
        def compose(self):
            """Compose the widget."""
            yield Static("📂 Files", id="file-popup-title")
            yield OptionList(id="file-popup-list")
            yield Static("↑↓ Navigate • Enter Select • Esc Cancel", id="file-popup-hint")
        
        def on_mount(self) -> None:
            """Handle mount."""
            self._update_list()
        
        def set_query(self, query: str, at_pos: int) -> None:
            """Set the search query."""
            self.filter_text = query
            self._at_pos = at_pos
        
        def watch_filter_text(self, value: str) -> None:
            """React to filter text changes."""
            self._update_list()
        
        def _update_list(self) -> None:
            """Update the file list based on filter."""
            if not self._file_service:
                return
            
            # Search files
            results = self._file_service.search(self.filter_text, max_results=15)
            
            self._files = [
                FileInfo(
                    path=r.path,
                    file_type=r.file_type,
                    score=r.score
                )
                for r in results
            ]
            
            # Update the option list
            try:
                option_list = self.query_one("#file-popup-list", OptionList)
                option_list.clear_options()
                
                for file_info in self._files:
                    text = Text()
                    text.append(file_info.icon, style="bold")
                    text.append(file_info.path, style="cyan" if file_info.file_type == "directory" else "")
                    
                    option_list.add_option(Option(text, id=file_info.path))
            except Exception:
                pass
        
        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            """Handle file selection from list."""
            if event.option.id:
                self._select_file(str(event.option.id))
        
        def on_key(self, event: events.Key) -> None:
            """Handle key events."""
            if event.key == "escape":
                self.post_message(self.Dismissed())
                event.stop()
            elif event.key == "enter":
                # Select first item if available
                if self._files:
                    self._select_file(self._files[0].path)
                event.stop()
        
        def _select_file(self, path: str) -> None:
            """Select a file and emit event."""
            self.post_message(self.FileSelected(path, self._at_pos))


else:
    class FilePopupWidget:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
