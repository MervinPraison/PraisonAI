"""
Command Popup Widget for PraisonAI TUI.

Shows a searchable list of available commands when user types backslash.
Inspired by Claude Code's command discovery UX.
"""

from typing import List, Optional, Callable
from dataclasses import dataclass

try:
    from textual.widget import Widget
    from textual.widgets import Static, Input, OptionList
    from textual.widgets.option_list import Option
    from textual.containers import Vertical, Container
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
class CommandInfo:
    """Information about a command for display."""
    name: str
    description: str
    aliases: List[str]
    category: str = "general"
    
    @property
    def display_name(self) -> str:
        """Get display name with aliases."""
        if self.aliases:
            return f"{self.name} ({', '.join(self.aliases)})"
        return self.name


if TEXTUAL_AVAILABLE:
    class CommandPopupWidget(Container):
        """
        Popup widget for command discovery and selection.
        
        Features:
        - Shows all available commands
        - Searchable/filterable
        - Keyboard navigation
        - Category grouping
        """
        
        DEFAULT_CSS = """
        CommandPopupWidget {
            layer: popup;
            width: 60;
            height: auto;
            max-height: 20;
            background: $surface;
            border: solid $primary;
            padding: 1;
            margin: 0 0 0 2;
        }
        
        CommandPopupWidget #popup-title {
            height: 1;
            background: $primary;
            color: $text;
            text-align: center;
            margin-bottom: 1;
        }
        
        CommandPopupWidget #popup-search {
            height: 3;
            margin-bottom: 1;
        }
        
        CommandPopupWidget #popup-list {
            height: auto;
            max-height: 12;
            background: $surface-darken-1;
        }
        
        CommandPopupWidget .command-item {
            padding: 0 1;
        }
        
        CommandPopupWidget .command-item:hover {
            background: $primary-darken-1;
        }
        
        CommandPopupWidget #popup-hint {
            height: 1;
            color: $text-muted;
            text-align: center;
            margin-top: 1;
        }
        """
        
        class CommandSelected(Message):
            """Event when a command is selected."""
            def __init__(self, command: str, args: str = ""):
                self.command = command
                self.args = args
                super().__init__()
        
        class Dismissed(Message):
            """Event when popup is dismissed."""
            pass
        
        # Reactive properties
        filter_text: reactive[str] = reactive("")
        
        def __init__(
            self,
            commands: Optional[List[CommandInfo]] = None,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._commands = commands or []
            self._filtered_commands: List[CommandInfo] = []
        
        def compose(self):
            """Compose the widget."""
            yield Static("Commands", id="popup-title")
            yield Input(placeholder="Type to filter...", id="popup-search")
            yield OptionList(id="popup-list")
            yield Static("↑↓ Navigate • Enter Select • Esc Cancel", id="popup-hint")
        
        def on_mount(self) -> None:
            """Handle mount."""
            self._update_list()
            # Focus the search input
            search = self.query_one("#popup-search", Input)
            search.focus()
        
        def set_commands(self, commands: List[CommandInfo]) -> None:
            """Set the available commands."""
            self._commands = commands
            self._update_list()
        
        def watch_filter_text(self, value: str) -> None:
            """React to filter text changes."""
            self._update_list()
        
        def _update_list(self) -> None:
            """Update the command list based on filter."""
            filter_lower = self.filter_text.lower()
            
            if filter_lower:
                self._filtered_commands = [
                    cmd for cmd in self._commands
                    if (filter_lower in cmd.name.lower() or
                        filter_lower in cmd.description.lower() or
                        any(filter_lower in alias.lower() for alias in cmd.aliases))
                ]
            else:
                self._filtered_commands = self._commands.copy()
            
            # Update the option list
            try:
                option_list = self.query_one("#popup-list", OptionList)
                option_list.clear_options()
                
                for cmd in self._filtered_commands:
                    # Create rich text for the option
                    text = Text()
                    text.append(f"/{cmd.name}", style="bold cyan")
                    if cmd.aliases:
                        text.append(f" ({', '.join(cmd.aliases)})", style="dim")
                    text.append(f"\n  {cmd.description}", style="")
                    
                    option_list.add_option(Option(text, id=cmd.name))
            except Exception:
                pass
        
        def on_input_changed(self, event: Input.Changed) -> None:
            """Handle search input changes."""
            if event.input.id == "popup-search":
                self.filter_text = event.value
        
        def on_input_submitted(self, event: Input.Submitted) -> None:
            """Handle Enter in search input."""
            if event.input.id == "popup-search":
                # Select first matching command
                if self._filtered_commands:
                    self._select_command(self._filtered_commands[0].name)
        
        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            """Handle command selection from list."""
            if event.option.id:
                self._select_command(str(event.option.id))
        
        def on_key(self, event: events.Key) -> None:
            """Handle key events."""
            if event.key == "escape":
                self.post_message(self.Dismissed())
                event.stop()
            elif event.key == "down":
                # Move focus to list if in search
                try:
                    option_list = self.query_one("#popup-list", OptionList)
                    option_list.focus()
                except Exception:
                    pass
            elif event.key == "up":
                # Move focus to search if at top of list
                try:
                    search = self.query_one("#popup-search", Input)
                    search.focus()
                except Exception:
                    pass
        
        def _select_command(self, command_name: str) -> None:
            """Select a command and emit event."""
            self.post_message(self.CommandSelected(command_name))
        
        def focus_search(self) -> None:
            """Focus the search input."""
            try:
                search = self.query_one("#popup-search", Input)
                search.focus()
            except Exception:
                pass


else:
    class CommandPopupWidget:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )


# Default commands list (matches slash_commands.py registry)
DEFAULT_COMMANDS = [
    CommandInfo("help", "Show help for commands", ["h", "?"]),
    CommandInfo("clear", "Clear conversation history", ["reset"]),
    CommandInfo("model", "Show or change the current model", ["m"]),
    CommandInfo("cost", "Show session cost and token usage", ["usage", "stats"]),
    CommandInfo("tokens", "Show token usage breakdown", []),
    CommandInfo("queue", "Show queue status", ["q"]),
    CommandInfo("cancel", "Cancel current operation", ["c"]),
    CommandInfo("settings", "Show current settings", ["set"]),
    CommandInfo("sessions", "Browse saved sessions", ["sess"]),
    CommandInfo("tools", "Toggle tools panel", ["t"]),
    CommandInfo("exit", "Exit the TUI", ["quit", "q"]),
    CommandInfo("plan", "Create an execution plan", []),
    CommandInfo("undo", "Undo the last change", []),
    CommandInfo("diff", "Show git diff of changes", []),
    CommandInfo("commit", "Commit changes with AI message", []),
    CommandInfo("map", "Show repository map", ["repo"]),
]


def get_default_commands() -> List[CommandInfo]:
    """Get the default command list."""
    return DEFAULT_COMMANDS.copy()
