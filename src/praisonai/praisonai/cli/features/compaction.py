"""
Context Compaction CLI Feature for PraisonAI.

Provides CLI commands for managing context compaction.

Commands:
- praisonai compaction status        # Show settings
- praisonai compaction set <strategy> # Set strategy
- praisonai compaction stats         # Show statistics
"""

import os
import json
from typing import Dict, Any


class CompactionHandler:
    """
    Handler for compaction CLI commands.
    
    Provides functionality to:
    - Show current compaction settings
    - Set compaction strategy (truncate, sliding, summarize, smart)
    - Display compaction statistics
    """
    
    CONFIG_FILE = ".praison/compaction.json"
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
    
    @property
    def feature_name(self) -> str:
        return "compaction"
    
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
        Show current compaction settings.
        
        Returns:
            Current compaction configuration
        """
        config = self._load_config()
        
        result = {
            "strategy": config.get("strategy", "truncate"),
            "max_tokens": config.get("max_tokens", 8000),
            "target_tokens": config.get("target_tokens", 6000),
            "preserve_system": config.get("preserve_system", True),
            "preserve_recent": config.get("preserve_recent", 5),
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
            
            table.add_row("Strategy", status["strategy"])
            table.add_row("Max Tokens", f"{status['max_tokens']:,}")
            table.add_row("Target Tokens", f"{status['target_tokens']:,}")
            table.add_row("Preserve System", "✓" if status["preserve_system"] else "✗")
            table.add_row("Preserve Recent", str(status["preserve_recent"]))
            table.add_row("Config File", status["config_file"])
            
            console.print(Panel(table, title="Context Compaction Status", border_style="blue"))
            
        except ImportError:
            print("Context Compaction Status:")
            print(f"  Strategy: {status['strategy']}")
            print(f"  Max Tokens: {status['max_tokens']:,}")
            print(f"  Target Tokens: {status['target_tokens']:,}")
            print(f"  Preserve System: {status['preserve_system']}")
            print(f"  Preserve Recent: {status['preserve_recent']}")
            print(f"  Config File: {status['config_file']}")
    
    def set_strategy(self, strategy: str) -> Dict[str, Any]:
        """
        Set compaction strategy.
        
        Args:
            strategy: Compaction strategy (truncate, sliding, summarize, smart)
            
        Returns:
            Updated configuration
        """
        valid_strategies = ["truncate", "sliding", "summarize", "smart"]
        strategy = strategy.lower()
        
        if strategy not in valid_strategies:
            self._print_error(f"Invalid strategy: {strategy}. Valid strategies: {', '.join(valid_strategies)}")
            return {"error": f"Invalid strategy: {strategy}"}
        
        config = self._load_config()
        config["strategy"] = strategy
        self._save_config(config)
        
        descriptions = {
            "truncate": "Remove oldest messages",
            "sliding": "Keep sliding window of recent messages",
            "summarize": "Summarize older messages",
            "smart": "Intelligent compaction based on importance"
        }
        
        result = {
            "strategy": strategy,
            "description": descriptions[strategy],
            "message": f"Compaction strategy set to '{strategy}'"
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
        Show compaction statistics.
        
        Returns:
            Compaction statistics
        """
        config = self._load_config()
        stats = config.get("stats", {})
        
        result = {
            "compaction_count": stats.get("compaction_count", 0),
            "total_tokens_saved": stats.get("total_tokens_saved", 0),
            "total_messages_removed": stats.get("total_messages_removed", 0),
            "average_compression_ratio": stats.get("average_compression_ratio", 0.0)
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
            
            if stats["compaction_count"] == 0:
                console.print("[yellow]No compaction operations recorded yet.[/yellow]")
                return
            
            table = Table(show_header=False, box=None)
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            
            table.add_row("Compactions", str(stats["compaction_count"]))
            table.add_row("Tokens Saved", f"{stats['total_tokens_saved']:,}")
            table.add_row("Messages Removed", str(stats["total_messages_removed"]))
            table.add_row("Avg Compression", f"{stats['average_compression_ratio']:.1%}")
            
            console.print(Panel(table, title="Compaction Statistics", border_style="blue"))
            
        except ImportError:
            print("Compaction Statistics:")
            print(f"  Compactions: {stats['compaction_count']}")
            print(f"  Tokens Saved: {stats['total_tokens_saved']:,}")
            print(f"  Messages Removed: {stats['total_messages_removed']}")
            print(f"  Avg Compression: {stats['average_compression_ratio']:.1%}")


def handle_compaction_command(args: list) -> int:
    """
    Handle compaction CLI commands.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code (0 for success)
    """
    if not args:
        args = ["status"]
    
    command = args[0].lower()
    handler = CompactionHandler()
    
    if command == "status":
        handler.status()
        return 0
    
    elif command == "set":
        if len(args) < 2:
            handler._print_error("Usage: praisonai compaction set <strategy>")
            print("Strategies: truncate, sliding, summarize, smart")
            return 1
        result = handler.set_strategy(args[1])
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
[bold]Context Compaction Commands[/bold]

[cyan]praisonai compaction status[/cyan]
    Show current compaction settings

[cyan]praisonai compaction set <strategy>[/cyan]
    Set compaction strategy
    
    Strategies:
    • truncate  - Remove oldest messages (default)
    • sliding   - Keep sliding window of recent messages
    • summarize - Summarize older messages
    • smart     - Intelligent compaction based on importance

[cyan]praisonai compaction stats[/cyan]
    Show compaction statistics

[cyan]praisonai compaction help[/cyan]
    Show this help message
"""
        console.print(Panel(help_text, title="Context Compaction Help", border_style="blue"))
        
    except ImportError:
        print("Context Compaction Commands:")
        print("  praisonai compaction status         - Show current settings")
        print("  praisonai compaction set <strategy> - Set compaction strategy")
        print("  praisonai compaction stats          - Show statistics")
        print("  praisonai compaction help           - Show this help")
        print("")
        print("Strategies: truncate, sliding, summarize, smart")
