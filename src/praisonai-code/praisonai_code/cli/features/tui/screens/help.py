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
            
            # Safe keyboard shortcuts section
            content.append("\n📋 Keyboard Shortcuts (Safe Defaults)\n", style="bold cyan")
            content.append("─" * 40 + "\n", style="dim")
            
            shortcuts = [
                ("\\", "Show command popup"),
                ("@path", "Reference file (type freely)"),
                ("/", "Show command discovery"),
                ("Enter", "Send message"),
                ("Shift+Enter", "New line in message"),
                ("q", "Quit (when not typing)"),
                ("?", "Show this help"),
                (":", "Enter command mode"),
                ("Escape", "Cancel/Close/Dismiss"),
                ("Tab", "Focus next element"),
                ("Up/Down", "Navigate history"),
            ]
            
            for key, desc in shortcuts:
                content.append(f"  {key:<15}", style="yellow")
                content.append(f" {desc}\n")
            
            # Command mode section
            content.append("\n⌨️  Command Mode (: prefix)\n", style="bold cyan")
            content.append("─" * 40 + "\n", style="dim")
            
            colon_cmds = [
                (":quit, :q", "Quit application"),
                (":clear, :cl", "Clear chat history"),
                (":help, :h", "Show help"),
                (":tools, :t", "Toggle tools panel"),
                (":queue, :qu", "Toggle queue panel"),
                (":settings", "Open settings"),
                (":cancel", "Cancel current operation"),
            ]
            
            for cmd, desc in colon_cmds:
                content.append(f"  {cmd:<15}", style="green")
                content.append(f" {desc}\n")
            
            # Slash commands section
            content.append("\n💬 Slash Commands (/ prefix)\n", style="bold cyan")
            content.append("─" * 40 + "\n", style="dim")
            
            commands = [
                ("/help", "Show help"),
                ("/clear", "Clear chat"),
                ("/model", "Show/change model"),
                ("/queue", "Show queue status"),
                ("/cancel", "Cancel current run"),
                ("/cost", "Show cost summary"),
                ("/settings", "Open settings"),
                ("/sessions", "Manage sessions"),
                ("/exit", "Exit TUI"),
            ]
            
            for cmd, desc in commands:
                content.append(f"  {cmd:<15}", style="green")
                content.append(f" {desc}\n")
            
            # Optional keys note
            content.append("\n⚙️  Optional Keys (disabled by default)\n", style="bold cyan")
            content.append("─" * 40 + "\n", style="dim")
            content.append("  Ctrl keys: ", style="dim")
            content.append("PRAISONAI_TUI_CTRL_KEYS=1\n", style="yellow")
            content.append("  Fn keys:   ", style="dim")
            content.append("PRAISONAI_TUI_FN_KEYS=1\n", style="yellow")
            
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
