"""
Interactive TUI System for PraisonAI CLI.

Inspired by Aider's interactive mode and prompt_toolkit usage.
Provides rich interactive terminal experience with completions and history.

Architecture:
- InteractiveSession: Main interactive session manager
- CommandCompleter: Auto-completion for commands and files
- HistoryManager: Persistent command history
- StatusDisplay: Rich-based status bar and output
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class InteractiveConfig:
    """Configuration for interactive session."""
    prompt: str = ">>> "
    multiline: bool = True
    history_file: Optional[str] = None
    max_history: int = 1000
    enable_completions: bool = True
    enable_syntax_highlighting: bool = True
    vi_mode: bool = False
    auto_suggest: bool = True
    show_status_bar: bool = True
    color_scheme: str = "monokai"


# ============================================================================
# Command Completer
# ============================================================================

class CommandCompleter:
    """
    Provides auto-completion for commands, files, and symbols.
    """
    
    def __init__(
        self,
        commands: Optional[List[str]] = None,
        file_patterns: Optional[List[str]] = None
    ):
        self.commands = commands or []
        self.file_patterns = file_patterns or ["*.py", "*.js", "*.ts"]
        self._file_cache: List[str] = []
        self._symbol_cache: List[str] = []
    
    def add_commands(self, commands: List[str]) -> None:
        """Add commands to completion list."""
        self.commands.extend(commands)
    
    def add_symbols(self, symbols: List[str]) -> None:
        """Add symbols to completion list."""
        self._symbol_cache.extend(symbols)
    
    def refresh_files(self, root: Optional[Path] = None) -> None:
        """Refresh file cache."""
        root = root or Path.cwd()
        self._file_cache = []
        
        for pattern in self.file_patterns:
            for file_path in root.rglob(pattern):
                try:
                    rel_path = str(file_path.relative_to(root))
                    if not any(excl in rel_path for excl in ["__pycache__", "node_modules", ".git"]):
                        self._file_cache.append(rel_path)
                except ValueError:
                    pass
    
    def get_completions(self, text: str, cursor_pos: int) -> List[str]:
        """
        Get completions for the current input.
        
        Args:
            text: Current input text
            cursor_pos: Cursor position
            
        Returns:
            List of completion suggestions
        """
        # Get word before cursor
        before_cursor = text[:cursor_pos]
        words = before_cursor.split()
        current_word = words[-1] if words else ""
        
        completions = []
        
        # Slash commands
        if current_word.startswith("/"):
            cmd_part = current_word[1:].lower()
            for cmd in self.commands:
                if cmd.lower().startswith(cmd_part):
                    completions.append(f"/{cmd}")
        
        # @ mentions for files
        elif current_word.startswith("@"):
            file_part = current_word[1:].lower()
            for file_path in self._file_cache:
                if file_part in file_path.lower():
                    completions.append(f"@{file_path}")
        
        # General completions
        else:
            word_lower = current_word.lower()
            
            # Check symbols
            for symbol in self._symbol_cache:
                if symbol.lower().startswith(word_lower):
                    completions.append(symbol)
            
            # Check files
            for file_path in self._file_cache:
                if word_lower in file_path.lower():
                    completions.append(file_path)
        
        return completions[:20]  # Limit results
    
    def create_prompt_toolkit_completer(self) -> Any:
        """Create a prompt_toolkit completer."""
        try:
            from prompt_toolkit.completion import Completer, Completion
            
            outer_self = self
            
            class PTCompleter(Completer):
                def get_completions(self, document, complete_event):
                    text = document.text
                    cursor_pos = document.cursor_position
                    
                    for completion in outer_self.get_completions(text, cursor_pos):
                        # Calculate start position
                        words = text[:cursor_pos].split()
                        current_word = words[-1] if words else ""
                        start_pos = -len(current_word)
                        
                        yield Completion(completion, start_position=start_pos)
            
            return PTCompleter()
        except ImportError:
            return None


# ============================================================================
# History Manager
# ============================================================================

class HistoryManager:
    """
    Manages command history with persistence.
    """
    
    def __init__(
        self,
        history_file: Optional[str] = None,
        max_entries: int = 1000
    ):
        self.history_file = Path(history_file) if history_file else None
        self.max_entries = max_entries
        self._history: List[str] = []
        self._position: int = 0
        
        if self.history_file:
            self._load_history()
    
    def _load_history(self) -> None:
        """Load history from file."""
        if self.history_file and self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self._history = [
                        line.strip() for line in f.readlines()
                        if line.strip()
                    ][-self.max_entries:]
            except Exception as e:
                logger.debug(f"Could not load history: {e}")
    
    def _save_history(self) -> None:
        """Save history to file."""
        if self.history_file:
            try:
                self.history_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.history_file, 'w', encoding='utf-8') as f:
                    for entry in self._history[-self.max_entries:]:
                        f.write(entry + "\n")
            except Exception as e:
                logger.debug(f"Could not save history: {e}")
    
    def add(self, entry: str) -> None:
        """Add an entry to history."""
        entry = entry.strip()
        if entry and (not self._history or self._history[-1] != entry):
            self._history.append(entry)
            self._position = len(self._history)
            self._save_history()
    
    def get_previous(self) -> Optional[str]:
        """Get previous history entry."""
        if self._position > 0:
            self._position -= 1
            return self._history[self._position]
        return None
    
    def get_next(self) -> Optional[str]:
        """Get next history entry."""
        if self._position < len(self._history) - 1:
            self._position += 1
            return self._history[self._position]
        elif self._position == len(self._history) - 1:
            self._position = len(self._history)
            return ""
        return None
    
    def search(self, prefix: str) -> List[str]:
        """Search history for entries starting with prefix."""
        return [
            entry for entry in self._history
            if entry.lower().startswith(prefix.lower())
        ]
    
    def get_all(self) -> List[str]:
        """Get all history entries."""
        return self._history.copy()
    
    def clear(self) -> None:
        """Clear history."""
        self._history.clear()
        self._position = 0
        if self.history_file and self.history_file.exists():
            self.history_file.unlink()
    
    def create_prompt_toolkit_history(self) -> Any:
        """Create a prompt_toolkit history object."""
        try:
            from prompt_toolkit.history import FileHistory, InMemoryHistory
            
            if self.history_file:
                return FileHistory(str(self.history_file))
            return InMemoryHistory()
        except ImportError:
            return None


# ============================================================================
# Status Display
# ============================================================================

class StatusDisplay:
    """
    Rich-based status display for interactive session.
    """
    
    def __init__(self, show_status_bar: bool = True):
        self.show_status_bar = show_status_bar
        self._console = None
        self._status_items: Dict[str, str] = {}
    
    @property
    def console(self):
        """Lazy load Rich console."""
        if self._console is None:
            try:
                from rich.console import Console
                self._console = Console()
            except ImportError:
                self._console = None
        return self._console
    
    def set_status(self, key: str, value: str) -> None:
        """Set a status item."""
        self._status_items[key] = value
    
    def clear_status(self, key: str) -> None:
        """Clear a status item."""
        self._status_items.pop(key, None)
    
    def print_status_bar(self) -> None:
        """Print the status bar."""
        if not self.show_status_bar or not self.console:
            return
        
        from rich.columns import Columns
        from rich.text import Text
        
        items = []
        for key, value in self._status_items.items():
            items.append(Text(f"{key}: {value}", style="dim"))
        
        if items:
            self.console.print(Columns(items, equal=True, expand=True))
    
    def print_welcome(self, version: str = "1.0.0") -> None:
        """Print welcome message."""
        if not self.console:
            print(f"PraisonAI CLI v{version}")
            return
        
        from rich.panel import Panel
        from rich.text import Text
        
        welcome = Text()
        welcome.append("PraisonAI CLI", style="bold cyan")
        welcome.append(f" v{version}\n", style="dim")
        welcome.append("Type ", style="dim")
        welcome.append("/help", style="bold green")
        welcome.append(" for commands, ", style="dim")
        welcome.append("/exit", style="bold yellow")
        welcome.append(" to quit", style="dim")
        
        self.console.print(Panel(welcome, border_style="blue"))
    
    def print_response(self, response: str, title: str = "Response") -> None:
        """Print a response with formatting."""
        if not self.console:
            print(response)
            return
        
        from rich.panel import Panel
        from rich.markdown import Markdown
        
        try:
            md = Markdown(response)
            self.console.print(Panel(md, title=title, border_style="green"))
        except Exception:
            self.console.print(Panel(response, title=title, border_style="green"))
    
    def print_error(self, error: str) -> None:
        """Print an error message."""
        if not self.console:
            print(f"Error: {error}")
            return
        
        from rich.panel import Panel
        self.console.print(Panel(error, title="Error", border_style="red"))
    
    def print_info(self, message: str) -> None:
        """Print an info message."""
        if not self.console:
            print(message)
            return
        
        self.console.print(f"[cyan]ℹ[/cyan] {message}")
    
    def print_success(self, message: str) -> None:
        """Print a success message."""
        if not self.console:
            print(message)
            return
        
        self.console.print(f"[green]✓[/green] {message}")


# ============================================================================
# Interactive Session
# ============================================================================

class InteractiveSession:
    """
    Main interactive session manager.
    
    Provides a rich interactive terminal experience with:
    - Command completion
    - History
    - Syntax highlighting
    - Status bar
    - Keyboard shortcuts
    """
    
    def __init__(
        self,
        config: Optional[InteractiveConfig] = None,
        on_input: Optional[Callable[[str], Optional[str]]] = None,
        on_command: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
    ):
        self.config = config or InteractiveConfig()
        self.on_input = on_input
        self.on_command = on_command
        
        self.completer = CommandCompleter()
        self.history = HistoryManager(
            history_file=self.config.history_file,
            max_entries=self.config.max_history
        )
        self.display = StatusDisplay(show_status_bar=self.config.show_status_bar)
        
        self._running = False
        self._prompt_session = None
    
    def _create_prompt_session(self) -> Any:
        """Create a prompt_toolkit session."""
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.lexers import PygmentsLexer
            from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
            from pygments.lexers import MarkdownLexer
            
            session_kwargs = {
                "message": self.config.prompt,
                "multiline": self.config.multiline,
            }
            
            # Add completer
            if self.config.enable_completions:
                completer = self.completer.create_prompt_toolkit_completer()
                if completer:
                    session_kwargs["completer"] = completer
            
            # Add history
            history = self.history.create_prompt_toolkit_history()
            if history:
                session_kwargs["history"] = history
            
            # Add syntax highlighting
            if self.config.enable_syntax_highlighting:
                session_kwargs["lexer"] = PygmentsLexer(MarkdownLexer)
            
            # Add auto-suggest
            if self.config.auto_suggest:
                session_kwargs["auto_suggest"] = AutoSuggestFromHistory()
            
            # VI mode
            if self.config.vi_mode:
                from prompt_toolkit.enums import EditingMode
                session_kwargs["editing_mode"] = EditingMode.VI
            
            return PromptSession(**session_kwargs)
        
        except ImportError as e:
            logger.debug(f"prompt_toolkit not available: {e}")
            return None
    
    def _get_input_fallback(self) -> str:
        """Fallback input method without prompt_toolkit."""
        try:
            if self.config.multiline:
                print(f"{self.config.prompt}(Enter empty line to submit)")
                lines = []
                while True:
                    line = input()
                    if not line:
                        break
                    lines.append(line)
                return "\n".join(lines)
            else:
                return input(self.config.prompt)
        except EOFError:
            return "/exit"
        except KeyboardInterrupt:
            print()
            return ""
    
    def get_input(self) -> str:
        """Get input from user."""
        if self._prompt_session:
            try:
                return self._prompt_session.prompt()
            except KeyboardInterrupt:
                return ""
            except EOFError:
                return "/exit"
        else:
            return self._get_input_fallback()
    
    def process_input(self, user_input: str) -> Optional[str]:
        """
        Process user input.
        
        Args:
            user_input: Raw user input
            
        Returns:
            Response string or None
        """
        user_input = user_input.strip()
        
        if not user_input:
            return None
        
        # Add to history
        self.history.add(user_input)
        
        # Check for slash commands
        if user_input.startswith("/"):
            if self.on_command:
                result = self.on_command(user_input)
                if result:
                    if result.get("type") == "exit":
                        self._running = False
                        return None
                    return result.get("message")
            return None
        
        # Regular input
        if self.on_input:
            return self.on_input(user_input)
        
        return None
    
    def run(self) -> None:
        """Run the interactive session."""
        self._running = True
        self._prompt_session = self._create_prompt_session()
        
        # Print welcome
        self.display.print_welcome()
        
        while self._running:
            try:
                # Get input
                user_input = self.get_input()
                
                # Process
                response = self.process_input(user_input)
                
                # Display response
                if response:
                    self.display.print_response(response)
                
            except KeyboardInterrupt:
                self.display.print_info("Use /exit to quit")
            except Exception as e:
                self.display.print_error(str(e))
                logger.exception("Error in interactive session")
    
    def stop(self) -> None:
        """Stop the interactive session."""
        self._running = False
    
    def add_commands(self, commands: List[str]) -> None:
        """Add commands for completion."""
        self.completer.add_commands(commands)
    
    def add_symbols(self, symbols: List[str]) -> None:
        """Add symbols for completion."""
        self.completer.add_symbols(symbols)
    
    def refresh_files(self, root: Optional[Path] = None) -> None:
        """Refresh file completions."""
        self.completer.refresh_files(root)


# ============================================================================
# CLI Integration Handler
# ============================================================================

class InteractiveTUIHandler:
    """
    Handler for integrating Interactive TUI with PraisonAI CLI.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._session: Optional[InteractiveSession] = None
    
    @property
    def feature_name(self) -> str:
        return "interactive_tui"
    
    def initialize(
        self,
        config: Optional[InteractiveConfig] = None,
        on_input: Optional[Callable[[str], Optional[str]]] = None,
        on_command: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None
    ) -> InteractiveSession:
        """Initialize the interactive session."""
        self._session = InteractiveSession(
            config=config,
            on_input=on_input,
            on_command=on_command
        )
        
        if self.verbose:
            from rich import print as rprint
            rprint("[cyan]Interactive TUI initialized[/cyan]")
        
        return self._session
    
    def get_session(self) -> Optional[InteractiveSession]:
        """Get the current session."""
        return self._session
    
    def run(self) -> None:
        """Run the interactive session."""
        if not self._session:
            self._session = self.initialize()
        
        self._session.run()
    
    def stop(self) -> None:
        """Stop the interactive session."""
        if self._session:
            self._session.stop()
