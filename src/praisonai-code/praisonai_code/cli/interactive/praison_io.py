"""
PraisonIO - Interactive CLI I/O handler inspired by Aider.

Key design principles:
1. prompt_toolkit used SYNCHRONOUSLY (never inside asyncio.run)
2. Rich for output rendering
3. MarkdownStream for flicker-free streaming
4. Clean separation of input/output concerns
"""

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

# Lazy imports for performance
_PROMPT_TOOLKIT_AVAILABLE = None
_RICH_AVAILABLE = None


def _check_prompt_toolkit():
    global _PROMPT_TOOLKIT_AVAILABLE
    if _PROMPT_TOOLKIT_AVAILABLE is None:
        try:
            import prompt_toolkit  # noqa: F401
            _PROMPT_TOOLKIT_AVAILABLE = True
        except ImportError:
            _PROMPT_TOOLKIT_AVAILABLE = False
    return _PROMPT_TOOLKIT_AVAILABLE


def _check_rich():
    global _RICH_AVAILABLE
    if _RICH_AVAILABLE is None:
        try:
            import rich  # noqa: F401
            _RICH_AVAILABLE = True
        except ImportError:
            _RICH_AVAILABLE = False
    return _RICH_AVAILABLE


@dataclass
class IOConfig:
    """Configuration for PraisonIO."""
    # Appearance
    pretty: bool = True
    user_input_color: str = "#00cc00"
    tool_output_color: str = "#0088ff"
    tool_error_color: str = "#ff0000"
    tool_warning_color: str = "#ffaa00"
    assistant_color: str = "#00aaff"
    
    # Input settings
    multiline_mode: bool = False
    vi_mode: bool = False
    
    # History
    input_history_file: Optional[str] = None
    
    # Completion
    enable_completions: bool = True
    
    # Streaming
    stream_delay: float = 0.05  # 20fps default


class PraisonCompleter:
    """Auto-completer for commands, files, and symbols."""
    
    def __init__(self, commands: Optional[Dict[str, str]] = None):
        self.commands = commands or {}
        self.files: Set[str] = set()
        self.symbols: Set[str] = set()
    
    def add_files(self, files: List[str]) -> None:
        """Add files to completion."""
        self.files.update(files)
    
    def add_symbols(self, symbols: List[str]) -> None:
        """Add symbols to completion."""
        self.symbols.update(symbols)
    
    def get_completions(self, text: str, cursor_pos: int) -> List[tuple]:
        """Get completions for current input."""
        before_cursor = text[:cursor_pos]
        words = before_cursor.split()
        current_word = words[-1] if words else ""
        
        completions = []
        
        # Slash commands
        if current_word.startswith("/"):
            cmd_part = current_word[1:].lower()
            for cmd, desc in self.commands.items():
                if cmd.lower().startswith(cmd_part):
                    completions.append((f"/{cmd}", desc))
        
        # @ file mentions
        elif current_word.startswith("@"):
            file_part = current_word[1:].lower()
            for f in self.files:
                if file_part in f.lower():
                    completions.append((f"@{f}", "file"))
        
        # General word completion
        elif current_word:
            word_lower = current_word.lower()
            for symbol in self.symbols:
                if symbol.lower().startswith(word_lower):
                    completions.append((symbol, "symbol"))
        
        return completions[:20]
    
    def create_prompt_toolkit_completer(self):
        """Create prompt_toolkit Completer."""
        if not _check_prompt_toolkit():
            return None
        
        from prompt_toolkit.completion import Completer, Completion
        
        outer = self
        
        class PTCompleter(Completer):
            def get_completions(self, document, complete_event):
                text = document.text
                cursor_pos = document.cursor_position
                
                for completion, meta in outer.get_completions(text, cursor_pos):
                    words = text[:cursor_pos].split()
                    current_word = words[-1] if words else ""
                    start_pos = -len(current_word)
                    yield Completion(completion, start_position=start_pos, display_meta=meta)
        
        return PTCompleter()


class MarkdownStream:
    """Flicker-free streaming markdown renderer.
    
    Uses Rich Live with a sliding window approach:
    - Stable lines print above the live area
    - Unstable lines (last N) render in the live window
    """
    
    def __init__(self, live_window: int = 6):
        self.live_window = live_window
        self.printed: List[str] = []
        self.live = None
        self._live_started = False
        self.min_delay = 1.0 / 20  # 20fps
        self.when = 0
    
    def _render_to_lines(self, text: str) -> List[str]:
        """Render markdown to lines."""
        if not _check_rich():
            return text.splitlines(keepends=True)
        
        import io
        from rich.console import Console
        from rich.markdown import Markdown
        
        string_io = io.StringIO()
        console = Console(file=string_io, force_terminal=True, width=100)
        console.print(Markdown(text))
        return string_io.getvalue().splitlines(keepends=True)
    
    def update(self, text: str, final: bool = False) -> None:
        """Update the streaming display."""
        if not _check_rich():
            # Fallback: just print
            print(text, end="" if not final else "\n", flush=True)
            return
        
        from rich.live import Live
        from rich.text import Text
        
        # Start live on first update
        if not self._live_started:
            self.live = Live(Text(""), refresh_per_second=20)
            self.live.start()
            self._live_started = True
        
        # Throttle updates
        now = time.time()
        if not final and now - self.when < self.min_delay:
            return
        self.when = now
        
        lines = self._render_to_lines(text)
        num_lines = len(lines)
        
        # Calculate stable lines
        if not final:
            num_lines -= self.live_window
        
        if final or num_lines > 0:
            num_printed = len(self.printed)
            show_count = num_lines - num_printed
            
            if show_count > 0:
                show = lines[num_printed:num_lines]
                show_text = "".join(show)
                self.live.console.print(Text.from_ansi(show_text), end="")
                self.printed = lines[:num_lines]
        
        if final:
            self.live.update(Text(""))
            self.live.stop()
            self.live = None
            return
        
        # Update live window
        rest = lines[num_lines:]
        rest_text = "".join(rest)
        self.live.update(Text.from_ansi(rest_text))
    
    def __del__(self):
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass


class PraisonIO:
    """
    Main I/O handler for PraisonAI interactive CLI.
    
    Inspired by Aider's io.py - handles all terminal I/O with:
    - Rich formatting for output
    - prompt_toolkit for input (with completions, history)
    - Streaming markdown rendering
    """
    
    def __init__(self, config: Optional[IOConfig] = None):
        self.config = config or IOConfig()
        self.completer = PraisonCompleter()
        self._console = None
        self._prompt_session = None
        self._history_file = None
        
        # Setup history file
        if self.config.input_history_file:
            self._history_file = Path(self.config.input_history_file)
        else:
            self._history_file = Path.home() / ".praison" / "input_history"
        
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
    
    @property
    def console(self):
        """Lazy-load Rich console."""
        if self._console is None and _check_rich():
            from rich.console import Console
            self._console = Console()
        return self._console
    
    def _create_prompt_session(self):
        """Create prompt_toolkit session."""
        if not _check_prompt_toolkit():
            return None
        
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.key_binding import KeyBindings
        
        kb = KeyBindings()
        
        # Ctrl+C to cancel current input
        @kb.add("c-c")
        def _(event):
            event.current_buffer.reset()
        
        # Alt+Enter for newline in multiline mode
        @kb.add("escape", "enter")
        def _(event):
            event.current_buffer.insert_text("\n")
        
        # Enter to submit (unless in multiline mode)
        @kb.add("enter")
        def _(event):
            if self.config.multiline_mode:
                event.current_buffer.insert_text("\n")
            else:
                event.current_buffer.validate_and_handle()
        
        # Ctrl+D to submit in multiline mode
        @kb.add("c-d")
        def _(event):
            event.current_buffer.validate_and_handle()
        
        session_kwargs = {
            "history": FileHistory(str(self._history_file)),
            "auto_suggest": AutoSuggestFromHistory(),
            "key_bindings": kb,
            "multiline": self.config.multiline_mode,
        }
        
        if self.config.enable_completions:
            completer = self.completer.create_prompt_toolkit_completer()
            if completer:
                from prompt_toolkit.completion import ThreadedCompleter
                session_kwargs["completer"] = ThreadedCompleter(completer)
        
        if self.config.vi_mode:
            from prompt_toolkit.enums import EditingMode
            session_kwargs["editing_mode"] = EditingMode.VI
        
        return PromptSession(**session_kwargs)
    
    def _get_style(self):
        """Get prompt_toolkit style."""
        if not _check_prompt_toolkit() or not self.config.pretty:
            return None
        
        from prompt_toolkit.styles import Style
        
        style_dict = {}
        if self.config.user_input_color:
            style_dict[""] = self.config.user_input_color
        
        return Style.from_dict(style_dict) if style_dict else None
    
    def get_input(self, prompt: str = "You: ") -> str:
        """
        Get input from user.
        
        This is SYNCHRONOUS - never call from inside asyncio.run().
        """
        if self._prompt_session is None:
            self._prompt_session = self._create_prompt_session()
        
        if self._prompt_session:
            try:
                style = self._get_style()
                return self._prompt_session.prompt(prompt, style=style)
            except KeyboardInterrupt:
                return ""
            except EOFError:
                return "/exit"
        else:
            # Fallback to basic input
            try:
                return input(prompt)
            except KeyboardInterrupt:
                return ""
            except EOFError:
                return "/exit"
    
    def rule(self) -> None:
        """Print a horizontal rule."""
        if self.console and self.config.pretty:
            self.console.rule(style=self.config.user_input_color)
        else:
            print()
    
    def print_welcome(self, model: str = "gpt-4o-mini", tools_count: int = 0, session_id: str = "") -> None:
        """Print welcome message."""
        if self.console and self.config.pretty:
            from rich.panel import Panel
            from rich.text import Text
            
            welcome = Text()
            welcome.append("PraisonAI Interactive Mode\n", style="bold cyan")
            welcome.append("Type your prompt, use ", style="dim")
            welcome.append("/help", style="bold green")
            welcome.append(" for commands, ", style="dim")
            welcome.append("/exit", style="bold yellow")
            welcome.append(" to quit\n", style="dim")
            welcome.append(f"Model: {model}", style="dim cyan")
            if tools_count:
                welcome.append(f" | Tools: {tools_count}", style="dim")
            if session_id:
                welcome.append(f" | Session: {session_id[:8]}", style="dim")
            
            self.console.print(Panel(welcome, border_style="blue", padding=(0, 1)))
        else:
            print("PraisonAI Interactive Mode")
            print("Type your prompt, use /help for commands, /exit to quit")
            print(f"Model: {model} | Tools: {tools_count}")
    
    def print_user_input(self, text: str) -> None:
        """Echo user input with styling."""
        if self.console and self.config.pretty:
            from rich.text import Text
            self.console.print(Text(text, style=self.config.user_input_color))
    
    def print_assistant_start(self) -> None:
        """Print assistant response start marker."""
        if self.console and self.config.pretty:
            self.console.print("\n[bold cyan]Assistant:[/bold cyan]")
        else:
            print("\nAssistant:")
    
    def print_assistant_response(self, response: str) -> None:
        """Print assistant response with markdown formatting."""
        if self.console and self.config.pretty:
            from rich.markdown import Markdown
            from rich.panel import Panel
            
            try:
                md = Markdown(response)
                self.console.print(Panel(md, border_style="cyan", padding=(0, 1)))
            except Exception:
                self.console.print(response)
        else:
            print(response)
    
    def stream_response(self, text: str, final: bool = False) -> MarkdownStream:
        """Get or update streaming response."""
        if not hasattr(self, '_current_stream') or self._current_stream is None:
            self._current_stream = MarkdownStream()
        
        self._current_stream.update(text, final=final)
        
        if final:
            self._current_stream = None
        
        return self._current_stream
    
    def tool_output(self, message: str) -> None:
        """Print tool output."""
        if self.console and self.config.pretty:
            self.console.print(f"[{self.config.tool_output_color}]⚙ {message}[/]")
        else:
            print(f"⚙ {message}")
    
    def tool_error(self, message: str) -> None:
        """Print tool error."""
        if self.console and self.config.pretty:
            self.console.print(f"[{self.config.tool_error_color}]✗ {message}[/]")
        else:
            print(f"✗ {message}", file=sys.stderr)
    
    def tool_warning(self, message: str) -> None:
        """Print tool warning."""
        if self.console and self.config.pretty:
            self.console.print(f"[{self.config.tool_warning_color}]⚠ {message}[/]")
        else:
            print(f"⚠ {message}", file=sys.stderr)
    
    def info(self, message: str) -> None:
        """Print info message."""
        if self.console and self.config.pretty:
            self.console.print(f"[dim]ℹ {message}[/dim]")
        else:
            print(f"ℹ {message}")
    
    def success(self, message: str) -> None:
        """Print success message."""
        if self.console and self.config.pretty:
            self.console.print(f"[green]✓ {message}[/green]")
        else:
            print(f"✓ {message}")
    
    def print_help(self, commands: Dict[str, str]) -> None:
        """Print help for available commands."""
        if self.console and self.config.pretty:
            from rich.table import Table
            
            table = Table(title="Available Commands", border_style="blue")
            table.add_column("Command", style="green")
            table.add_column("Description", style="dim")
            
            for cmd, desc in sorted(commands.items()):
                table.add_row(f"/{cmd}", desc)
            
            self.console.print(table)
        else:
            print("\nAvailable Commands:")
            for cmd, desc in sorted(commands.items()):
                print(f"  /{cmd:<12} - {desc}")
    
    def confirm(self, message: str, default: bool = False) -> bool:
        """Ask for confirmation."""
        suffix = " [Y/n]: " if default else " [y/N]: "
        
        if self.console and self.config.pretty:
            self.console.print(f"[yellow]? {message}[/yellow]", end="")
        
        try:
            response = input(suffix).strip().lower()
            if not response:
                return default
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
    
    def add_commands(self, commands: Dict[str, str]) -> None:
        """Add commands for completion."""
        self.completer.commands.update(commands)
    
    def add_files(self, files: List[str]) -> None:
        """Add files for completion."""
        self.completer.add_files(files)
    
    def add_symbols(self, symbols: List[str]) -> None:
        """Add symbols for completion."""
        self.completer.add_symbols(symbols)
