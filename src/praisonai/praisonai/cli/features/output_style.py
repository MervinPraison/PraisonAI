"""
Output Styles CLI Feature for PraisonAI.

Provides CLI commands for managing output styles.

Commands:
- praisonai output status        # Show current style
- praisonai output set <style>   # Set output style
"""

import os
import json
from typing import Dict, Any


class OutputStyleHandler:
    """
    Handler for output style CLI commands.
    
    Provides functionality to:
    - Show current output style settings
    - Set output style (concise, detailed, technical, conversational, structured, minimal)
    """
    
    CONFIG_FILE = ".praison/output.json"
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
    
    @property
    def feature_name(self) -> str:
        return "output"
    
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
        Show current output style settings.
        
        Returns:
            Current output style configuration
        """
        config = self._load_config()
        
        result = {
            "style": config.get("style", "default"),
            "format": config.get("format", "markdown"),
            "tone": config.get("tone", "professional"),
            "verbosity": config.get("verbosity", "normal"),
            "max_length": config.get("max_length"),
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
            
            table.add_row("Style", status["style"])
            table.add_row("Format", status["format"])
            table.add_row("Tone", status["tone"])
            table.add_row("Verbosity", status["verbosity"])
            table.add_row("Max Length", str(status["max_length"]) if status["max_length"] else "None")
            table.add_row("Config File", status["config_file"])
            
            console.print(Panel(table, title="Output Style Status", border_style="blue"))
            
        except ImportError:
            print("Output Style Status:")
            print(f"  Style: {status['style']}")
            print(f"  Format: {status['format']}")
            print(f"  Tone: {status['tone']}")
            print(f"  Verbosity: {status['verbosity']}")
            print(f"  Max Length: {status['max_length'] or 'None'}")
            print(f"  Config File: {status['config_file']}")
    
    def set_style(self, style: str) -> Dict[str, Any]:
        """
        Set output style.
        
        Args:
            style: Output style (concise, detailed, technical, conversational, structured, minimal)
            
        Returns:
            Updated configuration
        """
        valid_styles = ["concise", "detailed", "technical", "conversational", "structured", "minimal"]
        style = style.lower()
        
        if style not in valid_styles:
            self._print_error(f"Invalid style: {style}. Valid styles: {', '.join(valid_styles)}")
            return {"error": f"Invalid style: {style}"}
        
        # Style presets
        presets = {
            "concise": {
                "verbosity": "minimal",
                "target_length": 500,
                "include_examples": False
            },
            "detailed": {
                "verbosity": "verbose",
                "include_examples": True,
                "include_explanations": True
            },
            "technical": {
                "tone": "technical",
                "use_code_blocks": True,
                "include_examples": True
            },
            "conversational": {
                "tone": "friendly",
                "format": "plain",
                "use_headers": False
            },
            "structured": {
                "format": "markdown",
                "use_headers": True,
                "use_lists": True
            },
            "minimal": {
                "verbosity": "minimal",
                "target_length": 200,
                "use_headers": False,
                "include_examples": False
            }
        }
        
        config = self._load_config()
        config["style"] = style
        config.update(presets.get(style, {}))
        self._save_config(config)
        
        descriptions = {
            "concise": "Brief, direct responses",
            "detailed": "Thorough explanations with examples",
            "technical": "Developer-focused with code blocks",
            "conversational": "Friendly, casual tone",
            "structured": "Well-organized with headers and lists",
            "minimal": "Shortest possible responses"
        }
        
        result = {
            "style": style,
            "description": descriptions[style],
            "message": f"Output style set to '{style}'"
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


def handle_output_command(args: list) -> int:
    """
    Handle output CLI commands.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code (0 for success)
    """
    if not args:
        args = ["status"]
    
    command = args[0].lower()
    handler = OutputStyleHandler()
    
    if command == "status":
        handler.status()
        return 0
    
    elif command == "set":
        if len(args) < 2:
            handler._print_error("Usage: praisonai output set <style>")
            print("Styles: concise, detailed, technical, conversational, structured, minimal")
            return 1
        result = handler.set_style(args[1])
        return 0 if "error" not in result else 1
    
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
[bold]Output Style Commands[/bold]

[cyan]praisonai output status[/cyan]
    Show current output style settings

[cyan]praisonai output set <style>[/cyan]
    Set output style
    
    Styles:
    • concise        - Brief, direct responses
    • detailed       - Thorough explanations with examples
    • technical      - Developer-focused with code blocks
    • conversational - Friendly, casual tone
    • structured     - Well-organized with headers and lists
    • minimal        - Shortest possible responses

[cyan]praisonai output help[/cyan]
    Show this help message
"""
        console.print(Panel(help_text, title="Output Style Help", border_style="blue"))
        
    except ImportError:
        print("Output Style Commands:")
        print("  praisonai output status       - Show current settings")
        print("  praisonai output set <style>  - Set output style")
        print("  praisonai output help         - Show this help")
        print("")
        print("Styles: concise, detailed, technical, conversational, structured, minimal")
