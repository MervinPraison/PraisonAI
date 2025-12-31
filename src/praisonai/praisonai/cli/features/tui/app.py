"""
Main TUI Application for PraisonAI.

Event-loop driven async TUI with multi-pane layout.
"""

import asyncio
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.screen import Screen
    from textual import events
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    App = object

logger = logging.getLogger(__name__)


if TEXTUAL_AVAILABLE:
    from .screens.main import MainScreen
    from .screens.queue import QueueScreen
    from .screens.settings import SettingsScreen
    from .screens.session import SessionScreen
    from .widgets.chat import ChatMessage
    from .widgets.status import StatusInfo
    from .widgets.queue_panel import QueueItem
    from ..queue import QueueManager, QueueConfig, QueuedRun, RunPriority

    class TUIApp(App):
        """
        PraisonAI Terminal User Interface Application.
        
        Features:
        - Event-loop driven async UI
        - Multi-pane layout (chat, tools, queue, status)
        - Streaming output
        - Queue management
        - Session persistence
        """
        
        TITLE = "PraisonAI"
        SUB_TITLE = "AI Agent Terminal"
        
        CSS = """
        Screen {
            background: $surface;
        }
        """
        
        BINDINGS = [
            Binding("ctrl+q", "quit", "Quit", show=True, priority=True),
            Binding("ctrl+c", "cancel", "Cancel", show=True),
        ]
        
        SCREENS = {
            "main": MainScreen,
            "queue": QueueScreen,
            "settings": SettingsScreen,
            "sessions": SessionScreen,
        }
        
        def __init__(
            self,
            workspace: Optional[str] = None,
            session_id: Optional[str] = None,
            model: Optional[str] = None,
            agent_config: Optional[Dict[str, Any]] = None,
            queue_config: Optional[QueueConfig] = None,
            enable_acp: bool = True,
            enable_lsp: bool = True,
        ):
            super().__init__()
            
            self.workspace = workspace or os.getcwd()
            self.session_id = session_id or str(uuid.uuid4())[:8]
            self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            self.agent_config = agent_config or {}
            self.enable_acp = enable_acp
            self.enable_lsp = enable_lsp
            
            # Load default interactive tools (ACP + LSP) if not provided
            if "tools" not in self.agent_config or not self.agent_config["tools"]:
                self.agent_config["tools"] = self._load_default_tools()
            
            # Queue manager
            self.queue_config = queue_config or QueueConfig()
            self.queue_manager: Optional[QueueManager] = None
            
            # State
            self._current_run_id: Optional[str] = None
            self._streaming_content: str = ""
            self._total_tokens: int = 0
            self._total_cost: float = 0.0
            
            # Slash command handlers
            self._command_handlers: Dict[str, callable] = {}
            self._setup_commands()
        
        def _load_default_tools(self) -> list:
            """
            Load default interactive tools (ACP + LSP) for TUI.
            
            Uses the canonical interactive_tools provider.
            """
            try:
                from ..interactive_tools import get_interactive_tools, ToolConfig
                
                # Build disable list based on flags
                disable = []
                if not self.enable_acp:
                    disable.append('acp')
                if not self.enable_lsp:
                    disable.append('lsp')
                
                config = ToolConfig(
                    workspace=self.workspace,
                    enable_acp=self.enable_acp,
                    enable_lsp=self.enable_lsp,
                )
                
                tools = get_interactive_tools(
                    config=config,
                    disable=disable if disable else None,
                )
                
                logger.info(f"TUI loaded {len(tools)} default tools (ACP: {self.enable_acp}, LSP: {self.enable_lsp})")
                return tools
                
            except ImportError as e:
                logger.warning(f"Could not load interactive tools: {e}")
                return []
            except Exception as e:
                logger.error(f"Error loading default tools: {e}")
                return []
        
        def _setup_commands(self) -> None:
            """Setup slash command handlers."""
            self._command_handlers = {
                "help": self._cmd_help,
                "clear": self._cmd_clear,
                "model": self._cmd_model,
                "queue": self._cmd_queue,
                "cancel": self._cmd_cancel,
                "retry": self._cmd_retry,
                "settings": self._cmd_settings,
                "sessions": self._cmd_sessions,
                "cost": self._cmd_cost,
                "exit": self._cmd_exit,
                "quit": self._cmd_exit,
            }
        
        async def on_mount(self) -> None:
            """Handle app mount."""
            # Initialize queue manager with default tools (stored in runtime registry)
            self.queue_manager = QueueManager(
                config=self.queue_config,
                on_output=self._handle_output,
                on_complete=self._handle_complete,
                on_error=self._handle_error,
                default_tools=self.agent_config.get("tools", []),
            )
            
            await self.queue_manager.start(recover=True)
            self.queue_manager.set_session(self.session_id)
            
            # Push main screen
            await self.push_screen("main")
            
            # Update status
            self._update_status()
        
        async def on_unmount(self) -> None:
            """Handle app unmount."""
            if self.queue_manager:
                await self.queue_manager.stop()
        
        def compose(self) -> ComposeResult:
            """Compose the app."""
            yield from ()
        
        # Event handlers
        
        async def on_main_screen_message_submitted(
            self, event: MainScreen.MessageSubmitted
        ) -> None:
            """Handle message submission from main screen."""
            content = event.content
            
            # Add user message to chat
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                await main_screen.add_user_message(content)
                main_screen.set_processing(True)
            
            # Submit to queue
            # Note: tools are NOT included in config (they can't be JSON serialized)
            # Instead, they are stored in QueueManager._tools_registry and retrieved by worker
            try:
                run_id = await self.queue_manager.submit(
                    input_content=content,
                    agent_name=self.agent_config.get("name", "Assistant"),
                    config={
                        "agent_config": {
                            "name": self.agent_config.get("name", "Assistant"),
                            "instructions": self.agent_config.get(
                                "instructions", 
                                "You are a helpful AI assistant."
                            ),
                            "model": self.model,
                            "verbose": False,
                        }
                    }
                )
                
                self._current_run_id = run_id
                self._streaming_content = ""
                
                # Add streaming placeholder
                if isinstance(main_screen, MainScreen):
                    await main_screen.add_assistant_message(
                        content="",
                        run_id=run_id,
                        agent_name=self.agent_config.get("name", "Assistant"),
                        streaming=True,
                    )
                
            except Exception as e:
                logger.error(f"Failed to submit: {e}")
                if isinstance(main_screen, MainScreen):
                    main_screen.set_processing(False)
                    await main_screen.add_assistant_message(
                        content=f"Error: {e}",
                        agent_name="System",
                    )
            
            self._update_status()
        
        async def on_main_screen_command_executed(
            self, event: MainScreen.CommandExecuted
        ) -> None:
            """Handle command execution."""
            command = event.command.lower()
            args = event.args
            
            handler = self._command_handlers.get(command)
            if handler:
                await handler(args)
            else:
                # Unknown command
                main_screen = self.screen
                if isinstance(main_screen, MainScreen):
                    await main_screen.add_assistant_message(
                        content=f"Unknown command: /{command}\nType /help for available commands.",
                        agent_name="System",
                    )
        
        async def on_main_screen_cancel_requested(
            self, event: MainScreen.CancelRequested
        ) -> None:
            """Handle cancel request."""
            if self._current_run_id:
                await self.queue_manager.cancel(self._current_run_id)
                self._current_run_id = None
                
                main_screen = self.screen
                if isinstance(main_screen, MainScreen):
                    main_screen.set_processing(False)
                    await main_screen.add_assistant_message(
                        content="Operation cancelled.",
                        agent_name="System",
                    )
            
            self._update_status()
        
        async def on_queue_screen_run_cancelled(
            self, event: QueueScreen.RunCancelled
        ) -> None:
            """Handle run cancellation from queue screen."""
            await self.queue_manager.cancel(event.run_id)
            self._update_queue_screen()
        
        async def on_queue_screen_run_retried(
            self, event: QueueScreen.RunRetried
        ) -> None:
            """Handle run retry from queue screen."""
            await self.queue_manager.retry(event.run_id)
            self._update_queue_screen()
        
        async def on_queue_screen_queue_cleared(
            self, event: QueueScreen.QueueCleared
        ) -> None:
            """Handle queue clear."""
            await self.queue_manager.clear_queue()
            self._update_queue_screen()
        
        async def on_settings_screen_settings_saved(
            self, event: SettingsScreen.SettingsSaved
        ) -> None:
            """Handle settings save."""
            settings = event.settings
            
            if "model" in settings:
                self.model = settings["model"]
            
            if "max_concurrent" in settings:
                self.queue_config.max_concurrent_global = settings["max_concurrent"]
            
            if "autosave_interval" in settings:
                self.queue_config.autosave_interval_seconds = settings["autosave_interval"]
            
            self._update_status()
        
        async def on_session_screen_session_selected(
            self, event: SessionScreen.SessionSelected
        ) -> None:
            """Handle session selection."""
            self.session_id = event.session_id
            self.queue_manager.set_session(self.session_id)
            self._update_status()
        
        # Queue callbacks
        
        async def _handle_output(self, run_id: str, chunk: str) -> None:
            """Handle streaming output."""
            if run_id != self._current_run_id:
                return
            
            self._streaming_content += chunk
            
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                await main_screen.update_streaming(run_id, self._streaming_content)
        
        async def _handle_complete(self, run_id: str, run: QueuedRun) -> None:
            """Handle run completion."""
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                await main_screen.complete_streaming(
                    run_id, 
                    run.output_content or self._streaming_content
                )
                main_screen.set_processing(False)
            
            # Update metrics
            if run.metrics:
                self._total_tokens += run.metrics.get("tokens", 0)
                self._total_cost += run.metrics.get("cost", 0.0)
            
            if run_id == self._current_run_id:
                self._current_run_id = None
                self._streaming_content = ""
            
            self._update_status()
        
        async def _handle_error(self, run_id: str, error: Exception) -> None:
            """Handle run error."""
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                await main_screen.complete_streaming(run_id, f"Error: {error}")
                main_screen.set_processing(False)
            
            if run_id == self._current_run_id:
                self._current_run_id = None
                self._streaming_content = ""
            
            self._update_status()
        
        # Command handlers
        
        async def _cmd_help(self, args: str) -> None:
            """Show help."""
            help_text = """
**Available Commands:**

- `/help` - Show this help
- `/clear` - Clear chat history
- `/model [name]` - Show or set model
- `/queue` - Show queue screen
- `/cancel [run_id]` - Cancel a run
- `/retry [run_id]` - Retry a failed run
- `/settings` - Show settings
- `/sessions` - Browse sessions
- `/cost` - Show cost summary
- `/exit` or `/quit` - Exit TUI

**Keyboard Shortcuts:**

- `Ctrl+Enter` - Send message
- `Ctrl+C` - Cancel current operation
- `Ctrl+Q` - Quit
- `Ctrl+L` - Clear screen
- `F1` - Help
- `F2` - Toggle queue panel
- `F3` - Settings
- `F5` - Clear chat
- `Tab` - Cycle focus
- `Esc` - Cancel/close
"""
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                await main_screen.add_assistant_message(
                    content=help_text,
                    agent_name="Help",
                )
        
        async def _cmd_clear(self, args: str) -> None:
            """Clear chat."""
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                await main_screen.query_one("#chat-widget").clear()
        
        async def _cmd_model(self, args: str) -> None:
            """Show or set model."""
            main_screen = self.screen
            if args:
                self.model = args.strip()
                msg = f"Model set to: {self.model}"
            else:
                msg = f"Current model: {self.model}"
            
            if isinstance(main_screen, MainScreen):
                await main_screen.add_assistant_message(content=msg, agent_name="System")
            
            self._update_status()
        
        async def _cmd_queue(self, args: str) -> None:
            """Show queue screen."""
            await self.push_screen("queue")
            self._update_queue_screen()
        
        async def _cmd_cancel(self, args: str) -> None:
            """Cancel a run."""
            run_id = args.strip() if args else self._current_run_id
            if run_id:
                await self.queue_manager.cancel(run_id)
                main_screen = self.screen
                if isinstance(main_screen, MainScreen):
                    await main_screen.add_assistant_message(
                        content=f"Cancelled run: {run_id}",
                        agent_name="System",
                    )
            self._update_status()
        
        async def _cmd_retry(self, args: str) -> None:
            """Retry a failed run."""
            run_id = args.strip()
            if run_id:
                new_id = await self.queue_manager.retry(run_id)
                main_screen = self.screen
                if isinstance(main_screen, MainScreen):
                    if new_id:
                        await main_screen.add_assistant_message(
                            content=f"Retrying run {run_id} as {new_id}",
                            agent_name="System",
                        )
                    else:
                        await main_screen.add_assistant_message(
                            content=f"Cannot retry run: {run_id}",
                            agent_name="System",
                        )
            self._update_status()
        
        async def _cmd_settings(self, args: str) -> None:
            """Show settings."""
            await self.push_screen(SettingsScreen(current_settings={
                "model": self.model,
                "max_concurrent": self.queue_config.max_concurrent_global,
                "autosave_interval": int(self.queue_config.autosave_interval_seconds),
            }))
        
        async def _cmd_sessions(self, args: str) -> None:
            """Show sessions."""
            await self.push_screen("sessions")
        
        async def _cmd_cost(self, args: str) -> None:
            """Show cost summary."""
            msg = f"""
**Cost Summary:**

- Total Tokens: {self._total_tokens:,}
- Total Cost: ${self._total_cost:.4f}
- Session: {self.session_id}
"""
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                await main_screen.add_assistant_message(content=msg, agent_name="System")
        
        async def _cmd_exit(self, args: str) -> None:
            """Exit TUI."""
            self.exit()
        
        # Helper methods
        
        def _update_status(self) -> None:
            """Update status bar."""
            main_screen = self.screen
            if isinstance(main_screen, MainScreen):
                main_screen.update_status(StatusInfo(
                    session_id=self.session_id,
                    model=self.model,
                    total_tokens=self._total_tokens,
                    total_cost=self._total_cost,
                    queued_count=self.queue_manager.queued_count if self.queue_manager else 0,
                    running_count=self.queue_manager.running_count if self.queue_manager else 0,
                    is_processing=self._current_run_id is not None,
                ))
        
        def _update_queue_screen(self) -> None:
            """Update queue screen if visible."""
            if isinstance(self.screen, QueueScreen):
                runs = self.queue_manager.list_runs(limit=100)
                self.screen.update_runs([
                    {
                        "run_id": r.run_id,
                        "agent_name": r.agent_name,
                        "input": r.input_content,
                        "state": r.state.value,
                        "priority": r.priority.name.lower(),
                        "wait_time": f"{r.wait_seconds:.1f}s" if r.wait_seconds else "-",
                        "duration": f"{r.duration_seconds:.1f}s" if r.duration_seconds else "-",
                    }
                    for r in runs
                ])
        
        def action_quit(self) -> None:
            """Quit the application."""
            self.exit()
        
        def action_cancel(self) -> None:
            """Cancel current operation."""
            if self._current_run_id and self.queue_manager:
                asyncio.create_task(self.queue_manager.cancel(self._current_run_id))

else:
    class TUIApp:
        """Placeholder when Textual is not available."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "Textual is required for TUI. Install with: pip install praisonai[tui]"
            )


def run_tui(
    workspace: Optional[str] = None,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    agent_config: Optional[Dict[str, Any]] = None,
    enable_acp: bool = True,
    enable_lsp: bool = True,
) -> None:
    """
    Run the PraisonAI TUI.
    
    Args:
        workspace: Working directory.
        session_id: Session ID to resume.
        model: Default model.
        agent_config: Agent configuration.
        enable_acp: Enable ACP tools (default: True).
        enable_lsp: Enable LSP tools (default: True).
    """
    if not TEXTUAL_AVAILABLE:
        raise ImportError(
            "Textual is required for TUI. Install with: pip install praisonai[tui]"
        )
    
    app = TUIApp(
        workspace=workspace,
        session_id=session_id,
        model=model,
        agent_config=agent_config,
        enable_acp=enable_acp,
        enable_lsp=enable_lsp,
    )
    app.run()
