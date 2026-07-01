"""
PraisonAI Interactive TUI Application.

Full-screen terminal UI with:
- Sticky bottom input box (like Aider/Codex/Claude Code)
- Scrollable output area above
- ASCII art logo banner
- Status bar with model/context info
- Clean, spacious design inspired by Claude Code

Uses prompt_toolkit for the full-screen application.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# Lazy imports for performance
_PT_AVAILABLE = None
_RICH_AVAILABLE = None


def _check_prompt_toolkit():
    global _PT_AVAILABLE
    if _PT_AVAILABLE is None:
        try:
            import prompt_toolkit  # noqa: F401
            _PT_AVAILABLE = True
        except ImportError:
            _PT_AVAILABLE = False
    return _PT_AVAILABLE


def _check_rich():
    global _RICH_AVAILABLE
    if _RICH_AVAILABLE is None:
        try:
            import rich  # noqa: F401
            _RICH_AVAILABLE = True
        except ImportError:
            _RICH_AVAILABLE = False
    return _RICH_AVAILABLE


# ============================================================================
# Branding - Import from unified source
# ============================================================================

from praisonai.cli.branding import get_logo, get_version


# ============================================================================
# Color Scheme
# ============================================================================

@dataclass
class ColorScheme:
    """Color scheme for the TUI."""
    # Primary colors
    primary: str = "#00aaff"      # Cyan-blue (PraisonAI brand)
    secondary: str = "#888888"    # Gray
    accent: str = "#00cc00"       # Green
    
    # Text colors
    text: str = "#ffffff"         # White
    text_dim: str = "#666666"     # Dim gray
    text_muted: str = "#444444"   # Very dim
    
    # Status colors
    success: str = "#00cc00"      # Green
    warning: str = "#ffaa00"      # Orange
    error: str = "#ff4444"        # Red
    info: str = "#00aaff"         # Blue
    
    # UI elements
    border: str = "#333333"       # Dark gray
    input_bg: str = "#1a1a1a"     # Very dark
    output_bg: str = "#0d0d0d"    # Almost black


DEFAULT_COLORS = ColorScheme()


# ============================================================================
# TUI Configuration
# ============================================================================

@dataclass
class TUIConfig:
    """Configuration for the TUI application."""
    # Model settings
    model: str = "gpt-4o-mini"
    
    # Display settings
    show_logo: bool = True
    show_tips: bool = True
    show_status_bar: bool = True
    compact_mode: bool = False
    
    # Colors
    colors: ColorScheme = field(default_factory=ColorScheme)
    
    # Input settings
    multiline: bool = False
    vi_mode: bool = False
    
    # History
    history_file: Optional[str] = None
    
    # Session
    session_id: Optional[str] = None
    workspace: Optional[str] = None


# ============================================================================
# Message Types
# ============================================================================

@dataclass
class Message:
    """A chat message."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)


# ============================================================================
# TUI Application
# ============================================================================

class PraisonTUI:
    """
    Full-screen TUI application for PraisonAI.
    
    Features:
    - Sticky bottom input box
    - Scrollable output area
    - ASCII art logo
    - Status bar
    - Clean, spacious design
    """
    
    def __init__(self, config: Optional[TUIConfig] = None):
        self.config = config or TUIConfig()
        self.messages: List[Message] = []
        self._running = False
        self._agent = None
        self._total_tokens = 0
        self._total_cost = 0.0
        
        # Get terminal size
        self.term_width, self.term_height = shutil.get_terminal_size((80, 24))
        
        # Generate session ID
        import uuid
        self.session_id = self.config.session_id or str(uuid.uuid4())[:8]
    
    def _get_agent(self):
        """Lazy-load the agent."""
        if self._agent is None:
            try:
                from praisonaiagents import Agent
                
                self._agent = Agent(
                    name="PraisonAgent",
                    role="Assistant",
                    goal="Help the user with their requests",
                    instructions="You are a helpful AI assistant. Be concise and helpful.",
                    llm=self.config.model,
                )
            except ImportError as e:
                raise RuntimeError(f"Failed to import praisonaiagents: {e}")
        
        return self._agent
    
    def _render_logo(self) -> str:
        """Render the ASCII logo with colors."""
        if not self.config.show_logo:
            return ""
        
        logo = get_logo(self.term_width)
        version = get_version()
        
        info_line = f"v{version} · Model: {self.config.model} · Session: {self.session_id}"
        return logo.strip() + "\n" + info_line
    
    def _render_welcome(self) -> str:
        """Render welcome message."""
        lines = []
        
        # Logo
        if self.config.show_logo:
            lines.append(self._render_logo())
            lines.append("")
        
        # Tips
        if self.config.show_tips:
            tips = [
                "Type your message and press Enter to send",
                "Use /help for commands, /exit to quit",
                "Press ? for keyboard shortcuts",
            ]
            lines.append("  " + tips[0])
        
        lines.append("")
        
        return "\n".join(lines)
    
    def _render_status_bar(self) -> str:
        """Render the status bar."""
        if not self.config.show_status_bar:
            return ""
        
        left = f"? for shortcuts"
        center = f"{self.config.model}"
        right = f"Session: {self.session_id}"
        
        # Calculate spacing
        total_len = len(left) + len(center) + len(right)
        available = self.term_width - total_len - 4
        
        if available > 0:
            left_space = available // 2
            right_space = available - left_space
            return f" {left}{' ' * left_space}{center}{' ' * right_space}{right} "
        else:
            return f" {center} "
    
    def _format_message(self, msg: Message) -> str:
        """Format a message for display."""
        if msg.role == "user":
            prefix = "› "
            return f"{prefix}{msg.content}"
        elif msg.role == "assistant":
            prefix = "● "
            return f"{prefix}{msg.content}"
        elif msg.role == "tool":
            prefix = "⚙ "
            return f"{prefix}{msg.content}"
        else:
            return msg.content
    
    def _handle_command(self, command: str) -> bool:
        """Handle slash commands. Returns True if handled."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower().lstrip("/")
        args = parts[1] if len(parts) > 1 else ""
        
        if cmd in ("exit", "quit", "q"):
            self._running = False
            return True
        
        elif cmd == "help":
            help_text = """
Available Commands:
  /help          Show this help
  /exit, /quit   Exit interactive mode
  /clear         Clear conversation
  /model [name]  Show or change model
  /cost          Show token usage
  /compact       Toggle compact mode
  /multiline     Toggle multiline input
"""
            self.messages.append(Message(role="system", content=help_text.strip()))
            return True
        
        elif cmd == "clear":
            self.messages.clear()
            return True
        
        elif cmd == "model":
            if args:
                self.config.model = args
                self._agent = None
                self.messages.append(Message(role="system", content=f"Model changed to: {args}"))
            else:
                self.messages.append(Message(role="system", content=f"Current model: {self.config.model}"))
            return True
        
        elif cmd == "cost":
            self.messages.append(Message(
                role="system",
                content=f"Tokens: {self._total_tokens} | Cost: ${self._total_cost:.4f}"
            ))
            return True
        
        elif cmd == "compact":
            self.config.compact_mode = not self.config.compact_mode
            mode = "enabled" if self.config.compact_mode else "disabled"
            self.messages.append(Message(role="system", content=f"Compact mode {mode}"))
            return True
        
        elif cmd == "multiline":
            self.config.multiline = not self.config.multiline
            mode = "enabled" if self.config.multiline else "disabled"
            self.messages.append(Message(role="system", content=f"Multiline mode {mode}"))
            return True
        
        else:
            self.messages.append(Message(role="system", content=f"Unknown command: /{cmd}"))
            return True
    
    def _execute_prompt(self, prompt: str) -> Optional[str]:
        """Execute a prompt and return the response."""
        try:
            agent = self._get_agent()
            response = agent.start(prompt)
            return str(response) if response else None
        except Exception as e:
            return f"Error: {e}"
    
    def run(self) -> None:
        """Run the TUI application."""
        self._running = True
        
        # Print welcome
        print(self._render_welcome())
        
        # Setup history
        history_file = self.config.history_file or str(Path.home() / ".praison" / "history")
        Path(history_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Create prompt session
        if _check_prompt_toolkit():
            from prompt_toolkit import PromptSession
            from prompt_toolkit.history import FileHistory
            from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
            from prompt_toolkit.key_binding import KeyBindings
            from prompt_toolkit.styles import Style
            
            # Key bindings
            kb = KeyBindings()
            
            @kb.add("c-c")
            def _(event):
                event.current_buffer.reset()
            
            @kb.add("c-d")
            def _(event):
                if not event.current_buffer.text:
                    event.app.exit()
            
            # Style
            style = Style.from_dict({
                "": self.config.colors.accent,
                "prompt": self.config.colors.primary,
            })
            
            session = PromptSession(
                history=FileHistory(history_file),
                auto_suggest=AutoSuggestFromHistory(),
                key_bindings=kb,
                style=style,
                multiline=self.config.multiline,
            )
            
            def get_input():
                return session.prompt(
                    [("class:prompt", "› ")],
                    placeholder="Type your message or @path/to/file"
                )
        else:
            def get_input():
                return input("› ")
        
        # Main loop
        while self._running:
            try:
                # Print status bar
                if self.config.show_status_bar and not self.config.compact_mode:
                    status = self._render_status_bar()
                    if _check_rich():
                        from rich.console import Console
                        Console().print(f"[dim]{status}[/dim]")
                    else:
                        print(f"\033[90m{status}\033[0m")
                
                # Get input
                user_input = get_input().strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    self._handle_command(user_input)
                    # Print system messages
                    for msg in self.messages:
                        if msg.role == "system":
                            print(self._format_message(msg))
                    self.messages = [m for m in self.messages if m.role != "system"]
                    continue
                
                # Add user message
                self.messages.append(Message(role="user", content=user_input))
                
                # Show thinking indicator
                if _check_rich():
                    from rich.console import Console
                    Console().print("[dim]Thinking...[/dim]")
                
                # Execute
                response = self._execute_prompt(user_input)
                
                if response:
                    self.messages.append(Message(role="assistant", content=response))
                    
                    # Display response
                    if _check_rich():
                        from rich.console import Console
                        from rich.markdown import Markdown
                        from rich.panel import Panel
                        
                        console = Console()
                        try:
                            md = Markdown(response)
                            console.print(Panel(md, border_style="cyan", padding=(0, 1)))
                        except Exception:
                            console.print(f"● {response}")
                    else:
                        print(f"● {response}")
                
                print()  # Spacing
                
            except KeyboardInterrupt:
                print("\nUse /exit to quit")
            except EOFError:
                self._running = False
                print("\nGoodbye!")
            except Exception as e:
                print(f"Error: {e}")
        
        print("Goodbye!")
    
    def run_single(self, prompt: str) -> Optional[str]:
        """Run a single prompt."""
        return self._execute_prompt(prompt)


def start_tui(
    model: str = "gpt-4o-mini",
    show_logo: bool = True,
    compact: bool = False,
    **kwargs
) -> None:
    """Start the TUI application."""
    config = TUIConfig(
        model=model,
        show_logo=show_logo,
        compact_mode=compact,
    )
    
    tui = PraisonTUI(config=config)
    tui.run()
