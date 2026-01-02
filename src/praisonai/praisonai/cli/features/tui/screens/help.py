"""
Help Screen for PraisonAI TUI.

Displays keyboard shortcuts and usage information.
"""

from typing import Optional

try:
    from textual.screen import Screen
    from textual.containers import Vertical, Container
    from textual.widgets import Static, Footer, Button
    from textual.binding import Binding
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Screen = object


if TEXTUAL_AVAILABLE:
    from rich.text import Text
    from rich.panel import Panel
    from rich.table import Table

    class HelpScreen(Screen):
        """
        Help screen showing keyboard shortcuts and usage.
        """
        
        BINDINGS = [
            Binding("escape", "dismiss", "Close", show=True),
            Binding("q", "dismiss", "Close", show=True),
        ]
        
        DEFAULT_CSS = """
        HelpScreen {
            align: center middle;
        }
        
        HelpScreen #help-container {
            width: 80;
            height: auto;
            max-height: 90%;
            background: $surface;
            border: solid $primary;
            padding: 1 2;
        }
        
        HelpScreen #help-title {
            text-align: center;
            text-style: bold;
            margin-bottom: 1;
        }
        
        HelpScreen #close-button {
            margin-top: 1;
            width: 100%;
        }
        """
        
        def compose(self):
            """Compose the help screen."""
            with Container(id="help-container"):
                yield Static("PraisonAI TUI Help", id="help-title")
                yield Static(self._build_help_content())
                yield Button("Close (Esc)", id="close-button", variant="primary")
        
        def _build_help_content(self) -> Text:
            """Build the help content."""
            content = Text()
            
            # Keyboard shortcuts section
            content.append("\n📋 Keyboard Shortcuts\n", style="bold cyan")
            content.append("─" * 40 + "\n", style="dim")
            
            shortcuts = [
                ("Enter", "Send message"),
                ("Shift+Enter", "New line in message"),
                ("Ctrl+Q", "Quit application"),
                ("Ctrl+C", "Cancel current operation"),
                ("Ctrl+L", "Clear screen"),
                ("F1", "Show this help"),
                ("F2", "Toggle queue panel"),
                ("F3", "Open settings"),
                ("F5", "Clear chat history"),
                ("Tab", "Focus next element"),
                ("Escape", "Cancel/Close"),
                ("Up/Down", "Navigate history"),
            ]
            
            for key, desc in shortcuts:
                content.append(f"  {key:<15}", style="yellow")
                content.append(f" {desc}\n")
            
            # Commands section
            content.append("\n💬 Slash Commands\n", style="bold cyan")
            content.append("─" * 40 + "\n", style="dim")
            
            commands = [
                ("/help", "Show help"),
                ("/clear", "Clear chat"),
                ("/queue", "Show queue status"),
                ("/cancel", "Cancel current run"),
                ("/retry <id>", "Retry a failed run"),
                ("/settings", "Open settings"),
                ("/sessions", "Manage sessions"),
                ("/cost", "Show cost summary"),
                ("/exit", "Exit TUI"),
            ]
            
            for cmd, desc in commands:
                content.append(f"  {cmd:<15}", style="green")
                content.append(f" {desc}\n")
            
            # Tools section
            content.append("\n🔧 Available Tool Groups\n", style="bold cyan")
            content.append("─" * 40 + "\n", style="dim")
            
            tools = [
                ("ACP", "acp_create_file, acp_edit_file, acp_delete_file, acp_execute_command"),
                ("LSP", "lsp_list_symbols, lsp_find_definition, lsp_find_references"),
                ("Basic", "read_file, write_file, list_files, execute_command, internet_search"),
            ]
            
            for group, tool_list in tools:
                content.append(f"  {group:<8}", style="magenta bold")
                content.append(f" {tool_list}\n", style="dim")
            
            return content
        
        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle button press."""
            if event.button.id == "close-button":
                self.dismiss()
        
        def action_dismiss(self) -> None:
            """Dismiss the help screen."""
            self.dismiss()

else:
    class HelpScreen:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
