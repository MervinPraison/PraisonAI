"""
Slash Commands System for PraisonAI CLI.

Inspired by Aider's command system and Gemini CLI's slash commands.
Provides interactive commands like /help, /cost, /plan, /model, /clear, etc.

Architecture:
- SlashCommand: Base class for all commands
- SlashCommandRegistry: Manages command registration and lookup
- SlashCommandParser: Parses user input for slash commands
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CommandKind(Enum):
    """Type of slash command."""
    BUILT_IN = "built_in"
    CUSTOM = "custom"
    MCP = "mcp"


@dataclass
class SlashCommand:
    """
    Represents a slash command.
    
    Attributes:
        name: Primary command name (e.g., "help", "cost")
        description: Short description for help text
        action: Callable that executes the command
        alt_names: Alternative names/aliases
        sub_commands: Nested sub-commands
        kind: Type of command (built-in, custom, MCP)
        auto_execute: Whether to execute without confirmation
    """
    name: str
    description: str
    action: Optional[Callable[["CommandContext", str], Any]] = None
    alt_names: List[str] = field(default_factory=list)
    sub_commands: List["SlashCommand"] = field(default_factory=list)
    kind: CommandKind = CommandKind.BUILT_IN
    auto_execute: bool = True
    
    def __post_init__(self):
        """Validate command after initialization."""
        if not self.name:
            raise ValueError("Command name cannot be empty")
        if not self.name.isalnum() and "_" not in self.name and "-" not in self.name:
            raise ValueError(f"Invalid command name: {self.name}")


@dataclass
class CommandContext:
    """
    Context passed to command actions.
    
    Contains all services and state needed by commands.
    """
    # Core services
    agent: Any = None  # PraisonAI Agent instance
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Session state
    session_id: Optional[str] = None
    session_start_time: Optional[float] = None
    
    # Metrics
    total_tokens: int = 0
    total_cost: float = 0.0
    prompt_count: int = 0
    
    # UI callbacks
    print_fn: Callable[[str], None] = print
    input_fn: Callable[[str], str] = input
    
    # Command invocation info
    raw_input: str = ""
    command_name: str = ""
    args: str = ""


@dataclass
class ParsedSlashCommand:
    """Result of parsing a slash command."""
    command: Optional[SlashCommand] = None
    args: str = ""
    canonical_path: List[str] = field(default_factory=list)
    error: Optional[str] = None


class SlashCommandRegistry:
    """
    Registry for slash commands.
    
    Manages command registration, lookup, and help generation.
    """
    
    def __init__(self):
        self._commands: Dict[str, SlashCommand] = {}
        self._aliases: Dict[str, str] = {}  # alias -> primary name
    
    def register(self, command: SlashCommand) -> None:
        """Register a slash command."""
        if command.name in self._commands:
            logger.warning(f"Overwriting existing command: {command.name}")
        
        self._commands[command.name] = command
        
        # Register aliases
        for alias in command.alt_names:
            if alias in self._aliases:
                logger.warning(f"Alias '{alias}' already registered")
            self._aliases[alias] = command.name
    
    def unregister(self, name: str) -> bool:
        """Unregister a command by name."""
        if name in self._commands:
            cmd = self._commands.pop(name)
            # Remove aliases
            for alias in cmd.alt_names:
                self._aliases.pop(alias, None)
            return True
        return False
    
    def get(self, name: str) -> Optional[SlashCommand]:
        """Get a command by name or alias."""
        # Check primary name first
        if name in self._commands:
            return self._commands[name]
        # Check aliases
        if name in self._aliases:
            return self._commands.get(self._aliases[name])
        return None
    
    def get_all(self) -> List[SlashCommand]:
        """Get all registered commands."""
        return list(self._commands.values())
    
    def get_names(self) -> List[str]:
        """Get all command names (including aliases)."""
        names = list(self._commands.keys())
        names.extend(self._aliases.keys())
        return sorted(set(names))


class SlashCommandParser:
    """
    Parser for slash commands.
    
    Handles parsing of user input into command and arguments.
    """
    
    def __init__(self, registry: SlashCommandRegistry):
        self.registry = registry
    
    def is_slash_command(self, query: str) -> bool:
        """Check if input is a slash command."""
        query = query.strip()
        if not query.startswith('/'):
            return False
        # Exclude code comments
        if query.startswith('//') or query.startswith('/*'):
            return False
        return True
    
    def parse(self, query: str) -> ParsedSlashCommand:
        """
        Parse a slash command string.
        
        Args:
            query: Raw input string (e.g., "/help model" or "/cost")
            
        Returns:
            ParsedSlashCommand with resolved command and arguments
        """
        if not self.is_slash_command(query):
            return ParsedSlashCommand(error="Not a slash command")
        
        trimmed = query.strip()
        parts = trimmed[1:].strip().split()  # Remove leading /
        
        if not parts:
            return ParsedSlashCommand(error="Empty command")
        
        command_path = parts
        canonical_path: List[str] = []
        current_commands = self.registry.get_all()
        command_to_execute: Optional[SlashCommand] = None
        path_index = 0
        
        for part in command_path:
            # First pass: exact match on primary name
            found_command = None
            for cmd in current_commands:
                if cmd.name == part:
                    found_command = cmd
                    break
            
            # Second pass: check aliases
            if not found_command:
                for cmd in current_commands:
                    if part in cmd.alt_names:
                        found_command = cmd
                        break
            
            if found_command:
                command_to_execute = found_command
                canonical_path.append(found_command.name)
                path_index += 1
                if found_command.sub_commands:
                    current_commands = found_command.sub_commands
                else:
                    break
            else:
                break
        
        args = ' '.join(parts[path_index:])
        
        return ParsedSlashCommand(
            command=command_to_execute,
            args=args,
            canonical_path=canonical_path
        )


# ============================================================================
# Built-in Commands
# ============================================================================

def cmd_help(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show help for commands."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    if args:
        # Help for specific command
        registry = context.config.get("command_registry")
        if registry:
            cmd = registry.get(args)
            if cmd:
                console.print(f"\n[bold cyan]/{cmd.name}[/bold cyan]")
                console.print(f"  {cmd.description}")
                if cmd.alt_names:
                    console.print(f"  Aliases: {', '.join(cmd.alt_names)}")
                if cmd.sub_commands:
                    console.print("\n  Sub-commands:")
                    for sub in cmd.sub_commands:
                        console.print(f"    /{cmd.name} {sub.name} - {sub.description}")
                return {"type": "help", "command": cmd.name}
            else:
                console.print(f"[red]Unknown command: {args}[/red]")
                return {"type": "error", "message": f"Unknown command: {args}"}
    
    # General help
    table = Table(title="Available Commands", show_header=True)
    table.add_column("Command", style="cyan")
    table.add_column("Description")
    
    registry = context.config.get("command_registry")
    if registry:
        for cmd in registry.get_all():
            aliases = f" ({', '.join(cmd.alt_names)})" if cmd.alt_names else ""
            table.add_row(f"/{cmd.name}{aliases}", cmd.description)
    
    console.print(table)
    return {"type": "help"}


def cmd_cost(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show session cost and token usage."""
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    
    cost_info = f"""
[bold]Session Statistics[/bold]

Total Tokens: {context.total_tokens:,}
Total Cost: ${context.total_cost:.4f}
Prompts: {context.prompt_count}
"""
    
    if context.session_start_time:
        import time
        duration = time.time() - context.session_start_time
        minutes = int(duration // 60)
        seconds = int(duration % 60)
        cost_info += f"Duration: {minutes}m {seconds}s\n"
    
    console.print(Panel(cost_info, title="💰 Cost Tracker", border_style="green"))
    
    return {
        "type": "stats",
        "tokens": context.total_tokens,
        "cost": context.total_cost,
        "prompts": context.prompt_count
    }


def cmd_clear(context: CommandContext, args: str) -> Dict[str, Any]:
    """Clear the conversation history."""
    from rich.console import Console
    console = Console()
    
    # Reset agent conversation if available
    if context.agent and hasattr(context.agent, 'clear_history'):
        context.agent.clear_history()
    
    console.print("[green]✓ Conversation cleared[/green]")
    return {"type": "clear"}


def cmd_model(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show or change the current model."""
    from rich.console import Console
    console = Console()
    
    if args:
        # Change model
        if context.agent and hasattr(context.agent, 'set_model'):
            context.agent.set_model(args)
            console.print(f"[green]✓ Model changed to: {args}[/green]")
            return {"type": "model_change", "model": args}
        else:
            console.print(f"[yellow]Model change requested: {args}[/yellow]")
            return {"type": "model_change", "model": args}
    else:
        # Show current model
        current_model = "unknown"
        if context.agent and hasattr(context.agent, 'llm'):
            current_model = getattr(context.agent.llm, 'model', 'unknown')
        console.print(f"[cyan]Current model: {current_model}[/cyan]")
        return {"type": "model_info", "model": current_model}


def cmd_tokens(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show token usage breakdown."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    table = Table(title="Token Usage", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    table.add_row("Total Tokens", f"{context.total_tokens:,}")
    table.add_row("Prompts Sent", str(context.prompt_count))
    if context.prompt_count > 0:
        avg = context.total_tokens / context.prompt_count
        table.add_row("Avg Tokens/Prompt", f"{avg:.0f}")
    
    console.print(table)
    return {"type": "tokens", "total": context.total_tokens}


def cmd_plan(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show or create an execution plan."""
    from rich.console import Console
    console = Console()
    
    if args:
        console.print(f"[cyan]Creating plan for: {args}[/cyan]")
        # Trigger planning mode
        return {"type": "submit_prompt", "content": f"Create a detailed plan for: {args}"}
    else:
        console.print("[yellow]Usage: /plan <task description>[/yellow]")
        return {"type": "help", "command": "plan"}


def cmd_undo(context: CommandContext, args: str) -> Dict[str, Any]:
    """Undo the last change."""
    from rich.console import Console
    console = Console()
    
    # Check for git integration
    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD~1"],
            capture_output=True,
            text=True,
            cwd="."
        )
        if result.returncode == 0:
            console.print("[yellow]Last commit changes:[/yellow]")
            console.print(result.stdout)
            console.print("\n[cyan]Run 'git reset --soft HEAD~1' to undo[/cyan]")
        else:
            console.print("[red]No git history available[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    
    return {"type": "undo"}


def cmd_diff(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show git diff of changes."""
    from rich.console import Console
    from rich.syntax import Syntax
    
    console = Console()
    
    try:
        import subprocess
        result = subprocess.run(
            ["git", "diff"],
            capture_output=True,
            text=True,
            cwd="."
        )
        if result.stdout:
            syntax = Syntax(result.stdout, "diff", theme="monokai")
            console.print(syntax)
        else:
            console.print("[green]No uncommitted changes[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
    
    return {"type": "diff"}


def cmd_commit(context: CommandContext, args: str) -> Dict[str, Any]:
    """Commit changes with AI-generated message."""
    from rich.console import Console
    console = Console()
    
    console.print("[cyan]Generating commit message...[/cyan]")
    
    # This will trigger the commit command handler
    return {"type": "commit", "message": args if args else None}


def cmd_exit(context: CommandContext, args: str) -> Dict[str, Any]:
    """Exit the CLI."""
    from rich.console import Console
    console = Console()
    
    console.print("[yellow]Goodbye![/yellow]")
    return {"type": "exit"}


def cmd_settings(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show current settings."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    
    table = Table(title="Current Settings", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")
    
    for key, value in context.config.items():
        if key != "command_registry":  # Skip internal objects
            table.add_row(key, str(value))
    
    console.print(table)
    return {"type": "settings"}


def cmd_map(context: CommandContext, args: str) -> Dict[str, Any]:
    """Show repository map."""
    from rich.console import Console
    console = Console()
    
    console.print("[cyan]Generating repository map...[/cyan]")
    # This will be implemented with RepoMap feature
    return {"type": "map"}


# ============================================================================
# Registry Setup
# ============================================================================

def create_default_registry() -> SlashCommandRegistry:
    """Create registry with default built-in commands."""
    registry = SlashCommandRegistry()
    
    # Core commands
    registry.register(SlashCommand(
        name="help",
        description="Show help for commands",
        action=cmd_help,
        alt_names=["h", "?"]
    ))
    
    registry.register(SlashCommand(
        name="cost",
        description="Show session cost and token usage",
        action=cmd_cost,
        alt_names=["usage", "stats"]
    ))
    
    registry.register(SlashCommand(
        name="clear",
        description="Clear conversation history",
        action=cmd_clear,
        alt_names=["reset"]
    ))
    
    registry.register(SlashCommand(
        name="model",
        description="Show or change the current model",
        action=cmd_model,
        alt_names=["m"]
    ))
    
    registry.register(SlashCommand(
        name="tokens",
        description="Show token usage breakdown",
        action=cmd_tokens
    ))
    
    registry.register(SlashCommand(
        name="plan",
        description="Create an execution plan for a task",
        action=cmd_plan
    ))
    
    registry.register(SlashCommand(
        name="undo",
        description="Undo the last change",
        action=cmd_undo
    ))
    
    registry.register(SlashCommand(
        name="diff",
        description="Show git diff of changes",
        action=cmd_diff
    ))
    
    registry.register(SlashCommand(
        name="commit",
        description="Commit changes with AI-generated message",
        action=cmd_commit
    ))
    
    registry.register(SlashCommand(
        name="exit",
        description="Exit the CLI",
        action=cmd_exit,
        alt_names=["quit", "q"]
    ))
    
    registry.register(SlashCommand(
        name="settings",
        description="Show current settings",
        action=cmd_settings
    ))
    
    registry.register(SlashCommand(
        name="map",
        description="Show repository map",
        action=cmd_map,
        alt_names=["repo"]
    ))
    
    return registry


# ============================================================================
# Handler for CLI Integration
# ============================================================================

class SlashCommandHandler:
    """
    Handler for integrating slash commands with PraisonAI CLI.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.registry = create_default_registry()
        self.parser = SlashCommandParser(self.registry)
        self._context: Optional[CommandContext] = None
    
    def set_context(self, context: CommandContext) -> None:
        """Set the command context."""
        self._context = context
        context.config["command_registry"] = self.registry
    
    def is_command(self, query: str) -> bool:
        """Check if input is a slash command."""
        return self.parser.is_slash_command(query)
    
    def execute(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Execute a slash command.
        
        Returns:
            Command result dict or None if not a command
        """
        if not self.is_command(query):
            return None
        
        parsed = self.parser.parse(query)
        
        if parsed.error:
            if self.verbose:
                print(f"[red]Error: {parsed.error}[/red]")
            return {"type": "error", "message": parsed.error}
        
        if not parsed.command:
            return {"type": "error", "message": "Unknown command"}
        
        if not parsed.command.action:
            return {"type": "error", "message": f"Command '{parsed.command.name}' has no action"}
        
        # Create context if not set
        if not self._context:
            self._context = CommandContext()
            self._context.config["command_registry"] = self.registry
        
        self._context.raw_input = query
        self._context.command_name = parsed.command.name
        self._context.args = parsed.args
        
        try:
            result = parsed.command.action(self._context, parsed.args)
            return result
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {"type": "error", "message": str(e)}
    
    def register_command(self, command: SlashCommand) -> None:
        """Register a custom command."""
        self.registry.register(command)
    
    def get_completions(self, partial: str) -> List[str]:
        """Get command completions for partial input."""
        if not partial.startswith('/'):
            return []
        
        partial_cmd = partial[1:].lower()
        completions = []
        
        for name in self.registry.get_names():
            if name.lower().startswith(partial_cmd):
                completions.append(f"/{name}")
        
        return sorted(completions)
