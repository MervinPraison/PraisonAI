"""
Thinking Budgets CLI Feature for PraisonAI.

Provides CLI commands for managing thinking budgets.

Commands:
- praisonai thinking status      # Show current budget
- praisonai thinking set <level> # Set budget level
- praisonai thinking stats       # Show usage statistics
"""

import os
import json
from typing import Dict, Any


class ThinkingHandler:
    """
    Handler for thinking CLI commands.
    
    Provides functionality to:
    - Show current thinking budget settings
    - Set budget levels (minimal, low, medium, high, maximum)
    - Display usage statistics
    """
    
    CONFIG_FILE = ".praison/thinking.json"
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self._budget = None
        self._tracker = None
    
    @property
    def feature_name(self) -> str:
        return "thinking"
    
    def _get_config_path(self) -> str:
        """Get path to config file."""
        return os.path.join(os.getcwd(), self.CONFIG_FILE)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load config from file."""
        config_path = self._get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}
    
    def _save_config(self, config: Dict[str, Any]):
        """Save config to file."""
        config_path = self._get_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def status(self) -> Dict[str, Any]:
        """
        Show current thinking budget status.
        
        Returns:
            Current budget configuration
        """
        config = self._load_config()
        
        # Get current budget settings
        level = config.get("level", "medium")
        max_tokens = config.get("max_tokens", 8000)
        adaptive = config.get("adaptive", True)
        
        result = {
            "level": level,
            "max_tokens": max_tokens,
            "adaptive": adaptive,
            "config_file": self._get_config_path()
        }
        
        self._print_status(result)
        return result
    
    def _print_status(self, status: Dict[str, Any]):
        """Print status in formatted output."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            
            console = Console()
            
            table = Table(show_header=False, box=None)
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Level", status["level"])
            table.add_row("Max Tokens", str(status["max_tokens"]))
            table.add_row("Adaptive", "✓" if status["adaptive"] else "✗")
            table.add_row("Config File", status["config_file"])
            
            console.print(Panel(table, title="Thinking Budget Status", border_style="blue"))
            
        except ImportError:
            print("Thinking Budget Status:")
            print(f"  Level: {status['level']}")
            print(f"  Max Tokens: {status['max_tokens']}")
            print(f"  Adaptive: {status['adaptive']}")
            print(f"  Config File: {status['config_file']}")
    
    def set_level(self, level: str) -> Dict[str, Any]:
        """
        Set thinking budget level.
        
        Args:
            level: Budget level (minimal, low, medium, high, maximum)
            
        Returns:
            Updated configuration
        """
        valid_levels = ["minimal", "low", "medium", "high", "maximum"]
        level = level.lower()
        
        if level not in valid_levels:
            self._print_error(f"Invalid level: {level}. Valid levels: {', '.join(valid_levels)}")
            return {"error": f"Invalid level: {level}"}
        
        # Get token allocation for level
        token_map = {
            "minimal": 2000,
            "low": 4000,
            "medium": 8000,
            "high": 16000,
            "maximum": 32000
        }
        
        config = self._load_config()
        config["level"] = level
        config["max_tokens"] = token_map[level]
        self._save_config(config)
        
        result = {
            "level": level,
            "max_tokens": token_map[level],
            "message": f"Thinking budget set to {level} ({token_map[level]} tokens)"
        }
        
        self._print_success(result["message"])
        return result
    
    def _print_error(self, message: str):
        """Print error message."""
        try:
            from rich.console import Console
            Console().print(f"[red]Error: {message}[/red]")
        except ImportError:
            print(f"Error: {message}")
    
    def _print_success(self, message: str):
        """Print success message."""
        try:
            from rich.console import Console
            Console().print(f"[green]✓ {message}[/green]")
        except ImportError:
            print(f"✓ {message}")
    
    def stats(self) -> Dict[str, Any]:
        """
        Show thinking usage statistics.
        
        Returns:
            Usage statistics
        """
        config = self._load_config()
        stats = config.get("stats", {})
        
        result = {
            "session_count": stats.get("session_count", 0),
            "total_tokens_used": stats.get("total_tokens_used", 0),
            "total_time_seconds": stats.get("total_time_seconds", 0.0),
            "average_tokens_per_session": stats.get("average_tokens_per_session", 0.0),
            "average_utilization": stats.get("average_utilization", 0.0),
            "over_budget_count": stats.get("over_budget_count", 0)
        }
        
        self._print_stats(result)
        return result
    
    def _print_stats(self, stats: Dict[str, Any]):
        """Print statistics in formatted output."""
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
            
            console = Console()
            
            if stats["session_count"] == 0:
                console.print("[yellow]No thinking sessions recorded yet.[/yellow]")
                return
            
            table = Table(show_header=False, box=None)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Sessions", str(stats["session_count"]))
            table.add_row("Total Tokens Used", f"{stats['total_tokens_used']:,}")
            table.add_row("Total Time", f"{stats['total_time_seconds']:.1f}s")
            table.add_row("Avg Tokens/Session", f"{stats['average_tokens_per_session']:.0f}")
            table.add_row("Avg Utilization", f"{stats['average_utilization']:.1%}")
            table.add_row("Over Budget", str(stats["over_budget_count"]))
            
            console.print(Panel(table, title="Thinking Usage Statistics", border_style="blue"))
            
        except ImportError:
            print("Thinking Usage Statistics:")
            print(f"  Sessions: {stats['session_count']}")
            print(f"  Total Tokens Used: {stats['total_tokens_used']:,}")
            print(f"  Total Time: {stats['total_time_seconds']:.1f}s")
            print(f"  Avg Tokens/Session: {stats['average_tokens_per_session']:.0f}")
            print(f"  Avg Utilization: {stats['average_utilization']:.1%}")
            print(f"  Over Budget: {stats['over_budget_count']}")


def handle_thinking_command(args: list) -> int:
    """
    Handle thinking CLI commands.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code (0 for success)
    """
    if not args:
        args = ["status"]
    
    command = args[0].lower()
    handler = ThinkingHandler()
    
    if command == "status":
        handler.status()
        return 0
    
    elif command == "set":
        if len(args) < 2:
            handler._print_error("Usage: praisonai thinking set <level>")
            print("Levels: minimal, low, medium, high, maximum")
            return 1
        result = handler.set_level(args[1])
        return 0 if "error" not in result else 1
    
    elif command == "stats":
        handler.stats()
        return 0
    
    elif command == "help":
        _print_help()
        return 0
    
    else:
        handler._print_error(f"Unknown command: {command}")
        _print_help()
        return 1


def _print_help():
    """Print help message."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        
        console = Console()
        help_text = """
[bold]Thinking Budget Commands[/bold]

[cyan]praisonai thinking status[/cyan]
    Show current thinking budget settings

[cyan]praisonai thinking set <level>[/cyan]
    Set budget level (minimal, low, medium, high, maximum)
    
    Levels:
    • minimal  - 2,000 tokens
    • low      - 4,000 tokens
    • medium   - 8,000 tokens (default)
    • high     - 16,000 tokens
    • maximum  - 32,000 tokens

[cyan]praisonai thinking stats[/cyan]
    Show usage statistics

[cyan]praisonai thinking help[/cyan]
    Show this help message
"""
        console.print(Panel(help_text, title="Thinking Budget Help", border_style="blue"))
        
    except ImportError:
        print("Thinking Budget Commands:")
        print("  praisonai thinking status       - Show current settings")
        print("  praisonai thinking set <level>  - Set budget level")
        print("  praisonai thinking stats        - Show usage statistics")
        print("  praisonai thinking help         - Show this help")
        print("")
        print("Levels: minimal (2K), low (4K), medium (8K), high (16K), maximum (32K)")
