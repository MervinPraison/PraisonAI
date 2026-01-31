"""
CLI commands for Plugin Management.

Provides CLI commands for creating, listing, and managing single-file plugins.

Commands:
- init: Create a new plugin from template
- list: List discovered plugins
- load: Load a specific plugin
- discover: Discover and load all plugins from default directories
"""

import os
from pathlib import Path
from typing import Optional

try:
    import typer
    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False


def create_plugin_app():
    """Create the plugin CLI app."""
    if not HAS_TYPER:
        return None
    
    app = typer.Typer(
        name="plugin",
        help="Plugin management commands for creating and managing single-file plugins.",
        no_args_is_help=True,
    )
    
    @app.command("init")
    def init_command(
        name: str = typer.Argument(..., help="Name of the plugin to create"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory (default: ./.praison/plugins/)"),
        author: Optional[str] = typer.Option(None, "--author", "-a", help="Plugin author name"),
        description: Optional[str] = typer.Option(None, "--description", "-d", help="Plugin description"),
        with_hook: bool = typer.Option(False, "--with-hook", help="Include a sample hook"),
        force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing file"),
    ):
        """Create a new single-file plugin from template.
        
        Creates a WordPress-style plugin file with:
        - Docstring header with metadata
        - Sample @tool decorated function
        - Optional @add_hook decorated function
        
        Examples:
            praisonai plugin init weather_tools
            praisonai plugin init my_plugin --author "John Doe" --with-hook
            praisonai plugin init custom --output ./my_plugins/
        """
        try:
            from praisonaiagents.plugins.discovery import get_plugin_template, ensure_plugin_dir
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        # Determine output directory
        if output:
            plugin_dir = Path(output)
        else:
            plugin_dir = ensure_plugin_dir()
        
        # Create directory if needed
        plugin_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename from name
        filename = name.lower().replace(" ", "_").replace("-", "_")
        if not filename.endswith(".py"):
            filename = f"{filename}.py"
        
        plugin_path = plugin_dir / filename
        
        # Check if file exists
        if plugin_path.exists() and not force:
            typer.echo(f"Error: Plugin already exists: {plugin_path}", err=True)
            typer.echo("Use --force to overwrite.", err=True)
            raise typer.Exit(1)
        
        # Generate template
        template = get_plugin_template(
            name=name,
            description=description or f"A plugin that provides {name} functionality",
            author=author,
            include_hook=with_hook,
        )
        
        # Write file
        plugin_path.write_text(template)
        
        typer.echo(f"✓ Created plugin: {plugin_path}")
        typer.echo("")
        typer.echo("Next steps:")
        typer.echo(f"  1. Edit {plugin_path} to add your tools")
        typer.echo("  2. Tools will be auto-discovered when you run your agent")
        typer.echo("")
        typer.echo("Example usage in your code:")
        typer.echo("  from praisonaiagents import Agent")
        typer.echo(f"  agent = Agent(name='assistant', tools=['{filename[:-3]}'])")
    
    @app.command("list")
    def list_command(
        directory: Optional[str] = typer.Option(None, "--dir", "-d", help="Directory to scan (default: all default dirs)"),
        json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    ):
        """List all discovered plugins.
        
        Scans default plugin directories:
        - ./.praison/plugins/ (project-level)
        - ~/.praison/plugins/ (user-level)
        
        Examples:
            praisonai plugin list
            praisonai plugin list --json
            praisonai plugin list --dir ./my_plugins/
        """
        try:
            from praisonaiagents.plugins.discovery import discover_plugins, get_default_plugin_dirs
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        # Determine directories to scan
        if directory:
            dirs = [directory]
        else:
            dirs = [str(d) for d in get_default_plugin_dirs()]
            # Also check current project dir
            project_dir = Path.cwd() / ".praison" / "plugins"
            if project_dir.exists() and str(project_dir) not in dirs:
                dirs.insert(0, str(project_dir))
        
        if not dirs:
            typer.echo("No plugin directories found.")
            typer.echo("")
            typer.echo("Create a plugin directory:")
            typer.echo("  mkdir -p .praison/plugins")
            typer.echo("  # or")
            typer.echo("  mkdir -p ~/.praison/plugins")
            return
        
        # Discover plugins
        plugins = discover_plugins(dirs)
        
        if json_output:
            import json
            typer.echo(json.dumps(plugins, indent=2, default=str))
            return
        
        if not plugins:
            typer.echo("No plugins found.")
            typer.echo("")
            typer.echo("Scanned directories:")
            for d in dirs:
                typer.echo(f"  - {d}")
            typer.echo("")
            typer.echo("Create a plugin with:")
            typer.echo("  praisonai plugin init my_plugin")
            return
        
        typer.echo(f"Found {len(plugins)} plugin(s):\n")
        
        for plugin in plugins:
            name = plugin.get("name", "Unknown")
            version = plugin.get("version", "1.0.0")
            description = plugin.get("description", "")
            path = plugin.get("path", "")
            
            typer.echo(f"  • {name} (v{version})")
            if description and verbose:
                typer.echo(f"    {description}")
            if verbose:
                typer.echo(f"    Path: {path}")
            typer.echo("")
    
    @app.command("load")
    def load_command(
        path: str = typer.Argument(..., help="Path to the plugin file to load"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Load a specific plugin file.
        
        Loads a single-file plugin and registers its tools with the global registry.
        
        Examples:
            praisonai plugin load ./my_plugin.py
            praisonai plugin load ~/.praison/plugins/weather.py
        """
        try:
            from praisonaiagents.plugins.discovery import load_plugin
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        if not os.path.exists(path):
            typer.echo(f"Error: File not found: {path}", err=True)
            raise typer.Exit(1)
        
        if verbose:
            typer.echo(f"Loading plugin: {path}")
        
        result = load_plugin(path)
        
        if result is None:
            typer.echo("Error: Failed to load plugin", err=True)
            raise typer.Exit(1)
        
        name = result.get("name", "Unknown")
        tools = result.get("tools", [])
        
        typer.echo(f"✓ Loaded plugin: {name}")
        if tools:
            typer.echo(f"  Registered tools: {', '.join(tools)}")
        else:
            typer.echo("  No tools registered")
    
    @app.command("discover")
    def discover_command(
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    ):
        """Discover and load all plugins from default directories.
        
        Scans and loads plugins from:
        - ./.praison/plugins/ (project-level)
        - ~/.praison/plugins/ (user-level)
        
        Examples:
            praisonai plugin discover
            praisonai plugin discover --verbose
        """
        try:
            from praisonaiagents.plugins.discovery import discover_and_load_plugins
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        if verbose:
            typer.echo("Discovering plugins from default directories...")
        
        loaded = discover_and_load_plugins(plugin_dirs=None, include_defaults=True)
        
        if not loaded:
            typer.echo("No plugins found in default directories.")
            typer.echo("")
            typer.echo("Create a plugin with:")
            typer.echo("  praisonai plugin init my_plugin")
            return
        
        typer.echo(f"✓ Loaded {len(loaded)} plugin(s):\n")
        
        for plugin in loaded:
            name = plugin.get("name", "Unknown")
            tools = plugin.get("tools", [])
            typer.echo(f"  • {name}")
            if tools and verbose:
                typer.echo(f"    Tools: {', '.join(tools)}")
    
    @app.command("template")
    def template_command(
        with_hook: bool = typer.Option(False, "--with-hook", help="Include a sample hook"),
    ):
        """Print a plugin template to stdout.
        
        Useful for quick reference or piping to a file.
        
        Examples:
            praisonai plugin template
            praisonai plugin template > my_plugin.py
            praisonai plugin template --with-hook
        """
        try:
            from praisonaiagents.plugins.discovery import get_plugin_template
        except ImportError:
            typer.echo("Error: praisonaiagents not installed", err=True)
            raise typer.Exit(1)
        
        template = get_plugin_template(
            name="My Plugin",
            description="Description of what this plugin does",
            author="Your Name",
            include_hook=with_hook,
        )
        
        typer.echo(template)
    
    return app


# Create the app instance
plugin_app = create_plugin_app()
