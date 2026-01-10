"""
Rich/prompt_toolkit frontend for InteractiveCore.

This frontend provides a REPL-style interface using Rich for rendering
and prompt_toolkit for input handling.
"""

import asyncio
import logging
from typing import Optional

from ..core import InteractiveCore
from ..config import InteractiveConfig
from ..events import (
    InteractiveEvent,
    InteractiveEventType,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalDecision,
)

logger = logging.getLogger(__name__)


class RichFrontend:
    """
    Rich/prompt_toolkit frontend for interactive mode.
    
    This is used by:
    - `praisonai run --interactive`
    - `praisonai chat`
    """
    
    def __init__(
        self,
        core: Optional[InteractiveCore] = None,
        config: Optional[InteractiveConfig] = None,
        ui_config: Optional['UIConfig'] = None,
    ):
        """Initialize the Rich frontend.
        
        Args:
            core: InteractiveCore instance. If None, creates one.
            config: Configuration. Used if core is None.
            ui_config: UI backend configuration for rendering options.
        """
        self.core = core or InteractiveCore(config=config)
        self._ui_config = ui_config
        self._running = False
        self._current_response = ""
        self._pending_approval: Optional[ApprovalRequest] = None
        self._approval_event = asyncio.Event()
        self._approval_response: Optional[ApprovalResponse] = None
        
        # Subscribe to events
        self.core.subscribe(self._handle_event)
    
    def _handle_event(self, event: InteractiveEvent) -> None:
        """Handle events from InteractiveCore."""
        if event.type == InteractiveEventType.MESSAGE_START:
            self._on_message_start(event)
        elif event.type == InteractiveEventType.MESSAGE_CHUNK:
            self._on_message_chunk(event)
        elif event.type == InteractiveEventType.MESSAGE_END:
            self._on_message_end(event)
        elif event.type == InteractiveEventType.TOOL_START:
            self._on_tool_start(event)
        elif event.type == InteractiveEventType.TOOL_END:
            self._on_tool_end(event)
        elif event.type == InteractiveEventType.APPROVAL_ASKED:
            self._on_approval_asked(event)
        elif event.type == InteractiveEventType.ERROR:
            self._on_error(event)
        elif event.type == InteractiveEventType.SESSION_CREATED:
            self._on_session_created(event)
        elif event.type == InteractiveEventType.SESSION_RESUMED:
            self._on_session_resumed(event)
    
    def _on_message_start(self, event: InteractiveEvent) -> None:
        """Handle message start."""
        try:
            from rich.console import Console
            console = Console()
            console.print("\n[bold cyan]Assistant:[/bold cyan]", end=" ")
        except ImportError:
            print("\nAssistant:", end=" ")
    
    def _on_message_chunk(self, event: InteractiveEvent) -> None:
        """Handle message chunk (streaming)."""
        chunk = event.data.get("chunk", "")
        self._current_response += chunk
        print(chunk, end="", flush=True)
    
    def _on_message_end(self, event: InteractiveEvent) -> None:
        """Handle message end."""
        response = event.data.get("response", "")
        if response and not self._current_response:
            # Full response (non-streaming)
            print(response)
        else:
            print()  # Newline after streaming
        self._current_response = ""
    
    def _on_tool_start(self, event: InteractiveEvent) -> None:
        """Handle tool execution start."""
        tool_name = event.data.get("tool_name", "unknown")
        try:
            from rich.console import Console
            console = Console()
            console.print(f"[dim]⚙ Running {tool_name}...[/dim]")
        except ImportError:
            print(f"⚙ Running {tool_name}...")
    
    def _on_tool_end(self, event: InteractiveEvent) -> None:
        """Handle tool execution end."""
        tool_name = event.data.get("tool_name", "unknown")
        success = event.data.get("success", True)
        
        try:
            from rich.console import Console
            console = Console()
            if success:
                console.print(f"[dim]✓ {tool_name} completed[/dim]")
            else:
                console.print(f"[red]✗ {tool_name} failed[/red]")
        except ImportError:
            status = "✓" if success else "✗"
            print(f"{status} {tool_name} {'completed' if success else 'failed'}")
    
    def _on_approval_asked(self, event: InteractiveEvent) -> None:
        """Handle approval request."""
        self._pending_approval = ApprovalRequest(**event.data)
    
    def _on_error(self, event: InteractiveEvent) -> None:
        """Handle error."""
        error = event.data.get("error", "Unknown error")
        try:
            from rich.console import Console
            console = Console()
            console.print(f"[bold red]Error:[/bold red] {error}")
        except ImportError:
            print(f"Error: {error}")
    
    def _on_session_created(self, event: InteractiveEvent) -> None:
        """Handle session created."""
        session_id = event.data.get("session_id", "")
        try:
            from rich.console import Console
            console = Console()
            console.print(f"[dim]Session created: {session_id[:8]}...[/dim]")
        except ImportError:
            print(f"Session created: {session_id[:8]}...")
    
    def _on_session_resumed(self, event: InteractiveEvent) -> None:
        """Handle session resumed."""
        session_id = event.data.get("session_id", "")
        try:
            from rich.console import Console
            console = Console()
            console.print(f"[dim]Session resumed: {session_id[:8]}...[/dim]")
        except ImportError:
            print(f"Session resumed: {session_id[:8]}...")
    
    def _prompt_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        """Prompt user for approval decision."""
        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console()
            
            console.print(Panel(
                f"[bold]{request.description}[/bold]\n\n"
                f"Tool: {request.tool_name}\n"
                f"Action: {request.action_type}",
                title="[yellow]Approval Required[/yellow]",
                border_style="yellow"
            ))
            
            console.print("[1] Allow once")
            console.print("[2] Always allow this pattern")
            console.print("[3] Always allow for this session")
            console.print("[4] Reject")
            
        except ImportError:
            print(f"\n=== Approval Required ===")
            print(f"Description: {request.description}")
            print(f"Tool: {request.tool_name}")
            print(f"Action: {request.action_type}")
            print("[1] Allow once")
            print("[2] Always allow this pattern")
            print("[3] Always allow for this session")
            print("[4] Reject")
        
        while True:
            try:
                choice = input("\nChoice [1-4]: ").strip()
                
                if choice == "1":
                    return ApprovalResponse(
                        request_id=request.request_id,
                        decision=ApprovalDecision.ONCE
                    )
                elif choice == "2":
                    pattern = f"{request.action_type}:*"
                    return ApprovalResponse(
                        request_id=request.request_id,
                        decision=ApprovalDecision.ALWAYS,
                        remember_pattern=pattern
                    )
                elif choice == "3":
                    pattern = f"{request.action_type}:*"
                    return ApprovalResponse(
                        request_id=request.request_id,
                        decision=ApprovalDecision.ALWAYS_SESSION,
                        remember_pattern=pattern
                    )
                elif choice == "4":
                    return ApprovalResponse(
                        request_id=request.request_id,
                        decision=ApprovalDecision.REJECT
                    )
                else:
                    print("Invalid choice. Please enter 1-4.")
            except (EOFError, KeyboardInterrupt):
                return ApprovalResponse(
                    request_id=request.request_id,
                    decision=ApprovalDecision.REJECT
                )
    
    async def run(self) -> None:
        """Run the interactive REPL loop."""
        self._running = True
        
        try:
            from rich.console import Console
            console = Console()
            console.print("[bold green]PraisonAI Interactive Mode[/bold green]")
            console.print("[dim]Type /help for commands, /exit to quit[/dim]\n")
        except ImportError:
            print("PraisonAI Interactive Mode")
            print("Type /help for commands, /exit to quit\n")
        
        # Handle --continue flag
        if self.core.config.continue_session:
            session_id = self.core.continue_session()
            if not session_id:
                try:
                    from rich.console import Console
                    Console().print("[yellow]No previous session found. Starting new session.[/yellow]")
                except ImportError:
                    print("No previous session found. Starting new session.")
        
        # Try to use prompt_toolkit for better input
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.history import FileHistory
            from pathlib import Path
            
            history_file = Path.home() / ".praison" / "history"
            history_file.parent.mkdir(parents=True, exist_ok=True)
            
            session = PromptSession(history=FileHistory(str(history_file)))
            get_input = lambda: session.prompt("You: ")
        except ImportError:
            get_input = lambda: input("You: ")
        
        while self._running:
            try:
                user_input = get_input().strip()
                
                if not user_input:
                    continue
                
                # Handle slash commands
                if user_input.startswith("/"):
                    if await self._handle_command(user_input):
                        continue
                
                # Execute prompt
                await self.core.prompt(user_input)
                
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break
            except Exception as e:
                logger.exception("Error in REPL loop")
                try:
                    from rich.console import Console
                    Console().print(f"[red]Error: {e}[/red]")
                except ImportError:
                    print(f"Error: {e}")
    
    async def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if command was handled."""
        cmd = command.lower().split()[0]
        args = command.split()[1:] if len(command.split()) > 1 else []
        
        try:
            from rich.console import Console
            console = Console()
        except ImportError:
            console = None
        
        if cmd in ("/exit", "/quit", "/q"):
            self._running = False
            return True
        
        elif cmd == "/help":
            help_text = """
Available commands:
  /help          - Show this help
  /exit, /quit   - Exit interactive mode
  /clear         - Clear conversation history
  /session       - Show current session info
  /sessions      - List all sessions
  /continue      - Continue last session
  /export <file> - Export session to file
  /import <file> - Import session from file
  /model <name>  - Switch model
  /cost          - Show token/cost usage
"""
            if console:
                console.print(help_text)
            else:
                print(help_text)
            return True
        
        elif cmd == "/clear":
            # Create new session
            self.core.create_session()
            if console:
                console.print("[dim]Conversation cleared.[/dim]")
            else:
                print("Conversation cleared.")
            return True
        
        elif cmd == "/session":
            session_id = self.core.current_session_id
            if session_id:
                if console:
                    console.print(f"[dim]Current session: {session_id}[/dim]")
                else:
                    print(f"Current session: {session_id}")
            else:
                if console:
                    console.print("[dim]No active session[/dim]")
                else:
                    print("No active session")
            return True
        
        elif cmd == "/sessions":
            sessions = self.core.session_store.list_sessions()
            if sessions:
                if console:
                    console.print("[bold]Sessions:[/bold]")
                    for s in sessions[:10]:
                        sid = s.get("session_id", "")[:8]
                        title = s.get("title", "Untitled")
                        console.print(f"  {sid}... - {title}")
                else:
                    print("Sessions:")
                    for s in sessions[:10]:
                        print(f"  {s.get('session_id', '')[:8]}... - {s.get('title', 'Untitled')}")
            else:
                if console:
                    console.print("[dim]No sessions found[/dim]")
                else:
                    print("No sessions found")
            return True
        
        elif cmd == "/continue":
            session_id = self.core.continue_session()
            if session_id:
                if console:
                    console.print(f"[dim]Continued session: {session_id[:8]}...[/dim]")
                else:
                    print(f"Continued session: {session_id[:8]}...")
            else:
                if console:
                    console.print("[yellow]No previous session found[/yellow]")
                else:
                    print("No previous session found")
            return True
        
        elif cmd == "/export":
            if not args:
                if console:
                    console.print("[red]Usage: /export <filename>[/red]")
                else:
                    print("Usage: /export <filename>")
                return True
            
            session_id = self.core.current_session_id
            if session_id:
                try:
                    self.core.export_session_to_file(session_id, args[0])
                    if console:
                        console.print(f"[green]Session exported to {args[0]}[/green]")
                    else:
                        print(f"Session exported to {args[0]}")
                except Exception as e:
                    if console:
                        console.print(f"[red]Export failed: {e}[/red]")
                    else:
                        print(f"Export failed: {e}")
            else:
                if console:
                    console.print("[yellow]No active session to export[/yellow]")
                else:
                    print("No active session to export")
            return True
        
        elif cmd == "/import":
            if not args:
                if console:
                    console.print("[red]Usage: /import <filename>[/red]")
                else:
                    print("Usage: /import <filename>")
                return True
            
            try:
                session_id = self.core.import_session_from_file(args[0])
                self.core.resume_session(session_id)
                if console:
                    console.print(f"[green]Session imported: {session_id[:8]}...[/green]")
                else:
                    print(f"Session imported: {session_id[:8]}...")
            except Exception as e:
                if console:
                    console.print(f"[red]Import failed: {e}[/red]")
                else:
                    print(f"Import failed: {e}")
            return True
        
        elif cmd == "/model":
            if args:
                self.core.config.model = args[0]
                if console:
                    console.print(f"[dim]Model set to: {args[0]}[/dim]")
                else:
                    print(f"Model set to: {args[0]}")
            else:
                model = self.core.config.model or "default"
                if console:
                    console.print(f"[dim]Current model: {model}[/dim]")
                else:
                    print(f"Current model: {model}")
            return True
        
        elif cmd == "/cost":
            # TODO: Integrate with cost tracker
            if console:
                console.print("[dim]Cost tracking not yet implemented in unified core[/dim]")
            else:
                print("Cost tracking not yet implemented in unified core")
            return True
        
        return False  # Command not recognized
    
    def stop(self) -> None:
        """Stop the REPL loop."""
        self._running = False
