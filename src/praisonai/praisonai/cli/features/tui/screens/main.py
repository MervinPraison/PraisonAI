"""
Main Screen for PraisonAI TUI.

The primary chat interface screen.
"""

from typing import Optional

try:
    from textual.screen import Screen
    from textual.containers import Horizontal, Vertical, Container
    from textual.widgets import Static, Footer, Header
    from textual.binding import Binding
    from textual.message import Message
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Screen = object
    Message = object


if TEXTUAL_AVAILABLE:
    from ..widgets.chat import ChatWidget, ChatMessage
    from ..widgets.composer import ComposerWidget
    from ..widgets.status import StatusWidget, StatusInfo
    from ..widgets.queue_panel import QueuePanelWidget
    from ..widgets.tool_panel import ToolPanelWidget
    from ..config import TUIConfig, get_command, get_help_text

    class MainScreen(Screen):
        """
        Main chat screen.
        
        Layout:
        - Status bar (top)
        - Chat history (main area)
        - Tools panel (right sidebar)
        - Queue panel (right sidebar)
        - Composer (bottom)
        - Footer with keybindings
        """
        
        # Safe default bindings - no Ctrl or Fn keys by default
        # These work in VS Code, Windsurf, tmux, and plain terminals
        BINDINGS = [
            # Single-character shortcuts (safe defaults)
            Binding("q", "quit", "Quit", show=True, priority=True),
            Binding("question_mark", "help", "Help", show=True),
            Binding("colon", "command_mode", ":cmd", show=True),
            Binding("slash", "search", "/search", show=False),
            # Navigation
            Binding("tab", "focus_next", "Next", show=False),
            Binding("escape", "cancel_input", "Cancel", show=True),
        ]
        
        DEFAULT_CSS = """
        MainScreen {
            layout: grid;
            grid-size: 2;
            grid-columns: 3fr 1fr;
            grid-rows: 1 1fr auto 1;
        }
        
        MainScreen #status-bar {
            column-span: 2;
        }
        
        MainScreen #main-area {
            height: 100%;
        }
        
        MainScreen #sidebar {
            height: 100%;
        }
        
        MainScreen #composer-area {
            column-span: 2;
            height: auto;
            max-height: 10;
        }
        
        MainScreen Footer {
            column-span: 2;
        }
        
        MainScreen .sidebar-panel {
            height: 1fr;
        }
        """
        
        class MessageSubmitted(Message):
            """Event when a message is submitted."""
            def __init__(self, content: str):
                self.content = content
                super().__init__()
        
        class CommandExecuted(Message):
            """Event when a command is executed."""
            def __init__(self, command: str, args: str):
                self.command = command
                self.args = args
                super().__init__()
        
        class CancelRequested(Message):
            """Event when cancel is requested."""
            pass
        
        def __init__(
            self,
            show_queue: bool = True,
            show_tools: bool = True,
            config: Optional[TUIConfig] = None,
            name: Optional[str] = None,
            id: Optional[str] = None,
            classes: Optional[str] = None,
        ):
            super().__init__(name=name, id=id, classes=classes)
            self._show_queue = show_queue
            self._show_tools = show_tools
            self._config = config or TUIConfig.from_env()
            self._command_mode = False
            self._command_buffer = ""
            
            # Dynamically add Ctrl/Fn bindings if enabled
            self._setup_optional_bindings()
        
        def compose(self):
            """Compose the screen."""
            yield StatusWidget(id="status-bar")
            
            yield ChatWidget(id="chat-widget")
            
            with Vertical(id="sidebar"):
                if self._show_tools:
                    yield ToolPanelWidget(id="tool-panel", classes="sidebar-panel")
                if self._show_queue:
                    yield QueuePanelWidget(id="queue-panel", classes="sidebar-panel")
            
            yield ComposerWidget(id="composer")
            
            yield Footer()
        
        def _setup_optional_bindings(self) -> None:
            """Setup optional Ctrl/Fn key bindings based on config."""
            if self._config.enable_ctrl_keys:
                # Add Ctrl key bindings (opt-in)
                self._bindings.bind("ctrl+q", "quit", "^Q Quit", show=True)
                self._bindings.bind("ctrl+c", "cancel", "^C Cancel", show=True)
                self._bindings.bind("ctrl+l", "clear_chat", "^L Clear", show=True)
            
            if self._config.enable_fn_keys:
                # Add Function key bindings (opt-in)
                self._bindings.bind("f1", "help", "F1 Help", show=True)
                self._bindings.bind("f2", "toggle_queue", "F2 Queue", show=True)
                self._bindings.bind("f3", "settings", "F3 Settings", show=True)
                self._bindings.bind("f5", "clear_chat", "F5 Clear", show=True)
        
        def on_mount(self) -> None:
            """Handle mount."""
            # Focus composer
            composer = self.query_one("#composer", ComposerWidget)
            composer.focus_input()
        
        def on_composer_widget_submitted(self, event: ComposerWidget.Submitted) -> None:
            """Handle message submission."""
            if event.is_command:
                # Parse command (supports both / and : prefix)
                content = event.content
                if content.startswith("/") or content.startswith(":"):
                    content = content[1:]  # Remove prefix
                
                parts = content.split(maxsplit=1)
                command = parts[0] if parts else ""
                args = parts[1] if len(parts) > 1 else ""
                
                # Handle local screen commands first
                if self._handle_local_command(command, args):
                    return
                
                # Forward to app for other commands
                self.post_message(self.CommandExecuted(command, args))
            else:
                self.post_message(self.MessageSubmitted(event.content))
        
        def _handle_local_command(self, command: str, args: str) -> bool:
            """Handle commands that can be processed locally without app involvement."""
            cmd = get_command(command)
            
            if cmd == "quit":
                self.app.exit()
                return True
            elif cmd == "clear":
                self.action_clear_chat()
                return True
            elif cmd == "help":
                self.action_help()
                return True
            elif cmd == "tools":
                self.action_toggle_tools()
                return True
            elif cmd == "queue":
                self.action_toggle_queue()
                return True
            elif cmd == "settings":
                self.action_settings()
                return True
            elif cmd == "cancel":
                self.action_cancel()
                return True
            
            return False  # Not handled locally
        
        def action_quit(self) -> None:
            """Quit the application."""
            self.app.exit()
        
        def action_cancel(self) -> None:
            """Cancel current operation."""
            self.post_message(self.CancelRequested())
        
        def action_clear(self) -> None:
            """Clear screen."""
            pass
        
        def action_help(self) -> None:
            """Show help."""
            self.app.push_screen("help")
        
        def action_toggle_queue(self) -> None:
            """Toggle queue panel visibility."""
            try:
                queue_panel = self.query_one("#queue-panel", QueuePanelWidget)
                queue_panel.display = not queue_panel.display
            except Exception:
                pass
        
        def action_settings(self) -> None:
            """Show settings."""
            self.app.push_screen("settings")
        
        def action_clear_chat(self) -> None:
            """Clear chat history."""
            chat = self.query_one("#chat-widget", ChatWidget)
            self.app.call_later(chat.clear)
        
        def action_cancel_input(self) -> None:
            """Cancel current input."""
            composer = self.query_one("#composer", ComposerWidget)
            composer.action_cancel()
        
        def action_command_mode(self) -> None:
            """Enter command mode - focus composer with : prefix."""
            composer = self.query_one("#composer", ComposerWidget)
            composer.focus_input()
            composer.set_text(":")
        
        def action_search(self) -> None:
            """Enter search mode - focus composer with / prefix."""
            composer = self.query_one("#composer", ComposerWidget)
            composer.focus_input()
            composer.set_text("/")
        
        def action_toggle_tools(self) -> None:
            """Toggle tools panel visibility."""
            try:
                tool_panel = self.query_one("#tool-panel", ToolPanelWidget)
                tool_panel.display = not tool_panel.display
            except Exception:
                pass
        
        # Public methods for updating UI
        
        async def add_user_message(self, content: str) -> None:
            """Add a user message to chat."""
            chat = self.query_one("#chat-widget", ChatWidget)
            await chat.add_message(ChatMessage(
                role="user",
                content=content,
            ))
        
        async def add_assistant_message(
            self,
            content: str,
            run_id: Optional[str] = None,
            agent_name: Optional[str] = None,
            streaming: bool = False,
        ) -> None:
            """Add an assistant message to chat."""
            chat = self.query_one("#chat-widget", ChatWidget)
            await chat.add_message(ChatMessage(
                role="assistant",
                content=content,
                run_id=run_id,
                agent_name=agent_name,
                is_streaming=streaming,
            ))
        
        async def update_streaming(self, run_id: str, content: str) -> None:
            """Update streaming message."""
            chat = self.query_one("#chat-widget", ChatWidget)
            await chat.update_streaming(run_id, content)
        
        async def complete_streaming(self, run_id: str, content: str) -> None:
            """Complete streaming message."""
            chat = self.query_one("#chat-widget", ChatWidget)
            await chat.complete_streaming(run_id, content)
        
        def update_status(self, info: StatusInfo) -> None:
            """Update status bar."""
            status = self.query_one("#status-bar", StatusWidget)
            status.update_info(info)
        
        def set_processing(self, processing: bool) -> None:
            """Set processing state."""
            composer = self.query_one("#composer", ComposerWidget)
            composer.set_processing(processing)
            
            status = self.query_one("#status-bar", StatusWidget)
            status.is_processing = processing

else:
    class MainScreen:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )
