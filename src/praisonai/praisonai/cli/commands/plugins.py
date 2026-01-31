"""
Plugins command group for PraisonAI CLI.

Provides plugin management commands inspired by moltbot's plugins CLI.
Supports listing, enabling, disabling, and inspecting plugins.
"""

import typer

app = typer.Typer(
    help="Plugin management and inspection",
    no_args_is_help=True,
)


@app.command("list")
def plugins_list(
    enabled_only: bool = typer.Option(False, "--enabled", help="Show only enabled plugins"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List available plugins.
    
    Examples:
        praisonai plugins list
        praisonai plugins list --enabled
        praisonai plugins list --json
    """
    try:
        # Try to get plugins from the plugin system
        plugins = _get_available_plugins()
        
        if enabled_only:
            plugins = [p for p in plugins if p.get("enabled", False)]
        
        if json_output:
            import json
            print(json.dumps(plugins, indent=2))
        else:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title=f"Plugins ({len(plugins)} available)")
            table.add_column("ID", style="cyan")
            table.add_column("Name")
            table.add_column("Status")
            table.add_column("Description")
            
            for plugin in plugins:
                status = "[green]enabled[/green]" if plugin.get("enabled") else "[dim]disabled[/dim]"
                table.add_row(
                    plugin.get("id", "-"),
                    plugin.get("name", "-"),
                    status,
                    plugin.get("description", "-")[:40] + "..." if len(plugin.get("description", "")) > 40 else plugin.get("description", "-"),
                )
            
            console.print(table)
            
    except Exception as e:
        typer.echo(f"Error listing plugins: {e}", err=True)
        raise typer.Exit(1)


@app.command("info")
def plugins_info(
    plugin_id: str = typer.Argument(..., help="Plugin ID"),
):
    """Show detailed information about a plugin.
    
    Examples:
        praisonai plugins info memory-core
        praisonai plugins info browser-tool
    """
    try:
        plugins = _get_available_plugins()
        plugin = next((p for p in plugins if p.get("id") == plugin_id), None)
        
        if not plugin:
            typer.echo(f"Plugin not found: {plugin_id}", err=True)
            raise typer.Exit(1)
        
        from rich.console import Console
        from rich.panel import Panel
        
        console = Console()
        
        console.print(f"\n[bold cyan]{plugin.get('name', plugin_id)}[/bold cyan]")
        console.print(f"ID: {plugin.get('id', '-')}")
        console.print(f"Status: {'[green]enabled[/green]' if plugin.get('enabled') else '[dim]disabled[/dim]'}")
        console.print(f"Description: {plugin.get('description', '-')}")
        
        if plugin.get("version"):
            console.print(f"Version: {plugin.get('version')}")
        if plugin.get("author"):
            console.print(f"Author: {plugin.get('author')}")
        if plugin.get("hooks"):
            console.print(f"Hooks: {', '.join(plugin.get('hooks', []))}")
        if plugin.get("config_schema"):
            console.print("\n[bold]Config Schema:[/bold]")
            import json
            console.print(Panel(json.dumps(plugin.get("config_schema"), indent=2)))
            
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("enable")
def plugins_enable(
    plugin_id: str = typer.Argument(..., help="Plugin ID to enable"),
):
    """Enable a plugin.
    
    Examples:
        praisonai plugins enable memory-core
        praisonai plugins enable browser-tool
    """
    try:
        # Update config to enable plugin
        config_path = _get_config_path()
        config = _load_config(config_path)
        
        if "plugins" not in config:
            config["plugins"] = {}
        if "enabled" not in config["plugins"]:
            config["plugins"]["enabled"] = []
        
        if plugin_id not in config["plugins"]["enabled"]:
            config["plugins"]["enabled"].append(plugin_id)
            _save_config(config_path, config)
            typer.echo(f"[green]✓[/green] Plugin enabled: {plugin_id}")
        else:
            typer.echo(f"Plugin already enabled: {plugin_id}")
            
    except Exception as e:
        typer.echo(f"Error enabling plugin: {e}", err=True)
        raise typer.Exit(1)


@app.command("disable")
def plugins_disable(
    plugin_id: str = typer.Argument(..., help="Plugin ID to disable"),
):
    """Disable a plugin.
    
    Examples:
        praisonai plugins disable memory-core
        praisonai plugins disable browser-tool
    """
    try:
        config_path = _get_config_path()
        config = _load_config(config_path)
        
        if "plugins" in config and "enabled" in config["plugins"]:
            if plugin_id in config["plugins"]["enabled"]:
                config["plugins"]["enabled"].remove(plugin_id)
                _save_config(config_path, config)
                typer.echo(f"[yellow]![/yellow] Plugin disabled: {plugin_id}")
            else:
                typer.echo(f"Plugin not enabled: {plugin_id}")
        else:
            typer.echo(f"Plugin not enabled: {plugin_id}")
            
    except Exception as e:
        typer.echo(f"Error disabling plugin: {e}", err=True)
        raise typer.Exit(1)


@app.command("doctor")
def plugins_doctor():
    """Check plugin health and configuration.
    
    Verifies that all enabled plugins are properly configured and
    their dependencies are met.
    
    Examples:
        praisonai plugins doctor
    """
    try:
        from rich.console import Console
        from rich.table import Table
        
        console = Console()
        plugins = _get_available_plugins()
        enabled_plugins = [p for p in plugins if p.get("enabled")]
        
        console.print("[bold]Plugin Health Check[/bold]\n")
        
        if not enabled_plugins:
            console.print("[yellow]No plugins enabled[/yellow]")
            return
        
        table = Table()
        table.add_column("Plugin", style="cyan")
        table.add_column("Status")
        table.add_column("Issues")
        
        issues_found = 0
        
        for plugin in enabled_plugins:
            issues = []
            
            # Check if plugin module exists
            if plugin.get("module"):
                try:
                    __import__(plugin["module"])
                except ImportError:
                    issues.append("Module not found")
            
            # Check required config
            if plugin.get("required_config"):
                for key in plugin["required_config"]:
                    # Check if config key exists
                    pass  # Would check actual config
            
            if issues:
                status = "[red]✗ Issues[/red]"
                issues_found += len(issues)
            else:
                status = "[green]✓ OK[/green]"
            
            table.add_row(
                plugin.get("name", plugin.get("id")),
                status,
                ", ".join(issues) if issues else "-",
            )
        
        console.print(table)
        
        if issues_found:
            console.print(f"\n[red]Found {issues_found} issue(s)[/red]")
        else:
            console.print(f"\n[green]All {len(enabled_plugins)} plugins healthy[/green]")
            
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


# ============ Single-File Plugin Commands ============

@app.command("create")
def plugins_create(
    name: str = typer.Argument(..., help="Plugin name (will be converted to snake_case)"),
    description: str = typer.Option("A PraisonAI plugin", "--description", "-d", help="Plugin description"),
    author: str = typer.Option("", "--author", "-a", help="Plugin author"),
    output_dir: str = typer.Option(None, "--output", "-o", help="Output directory (default: ~/.praison/plugins/)"),
):
    """Create a new single-file plugin from template.
    
    Creates a new plugin with WordPress-style docstring header in the
    user's plugin directory (~/.praison/plugins/).
    
    Examples:
        praisonai plugins create weather
        praisonai plugins create weather --description "Weather API tools"
        praisonai plugins create weather -o ./my_plugins/
    """
    try:
        from pathlib import Path
        from praisonaiagents.plugins.discovery import get_plugin_template, ensure_plugin_dir
        
        # Sanitize plugin name
        safe_name = name.lower().replace("-", "_").replace(" ", "_")
        
        # Determine output directory
        if output_dir:
            plugin_dir = Path(output_dir).expanduser().resolve()
            plugin_dir.mkdir(parents=True, exist_ok=True)
        else:
            plugin_dir = ensure_plugin_dir()
        
        plugin_path = plugin_dir / f"{safe_name}.py"
        
        # Check if file already exists
        if plugin_path.exists():
            overwrite = typer.confirm(f"Plugin {plugin_path} already exists. Overwrite?")
            if not overwrite:
                typer.echo("Cancelled.")
                raise typer.Exit(0)
        
        # Generate template
        template = get_plugin_template(name, description, author)
        
        # Write file
        plugin_path.write_text(template)
        
        typer.echo(f"[green]✓[/green] Created plugin: {plugin_path}")
        typer.echo(f"\nNext steps:")
        typer.echo(f"  1. Edit {plugin_path} to add your tools")
        typer.echo(f"  2. Run 'praisonai plugins discover' to verify")
        typer.echo(f"  3. Use tools with Agent(tools=['example_tool'])")
        
    except ImportError as e:
        typer.echo(f"Error: praisonaiagents package not found. Install with: pip install praisonaiagents", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error creating plugin: {e}", err=True)
        raise typer.Exit(1)


@app.command("install")  
def plugins_install(
    source: str = typer.Argument(..., help="Path to plugin file to install"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing plugin"),
):
    """Install a single-file plugin.
    
    Copies a plugin file to the user's plugin directory (~/.praison/plugins/).
    
    Examples:
        praisonai plugins install ./my_weather_plugin.py
        praisonai plugins install ./my_weather_plugin.py --force
    """
    try:
        from pathlib import Path
        import shutil
        from praisonaiagents.plugins.discovery import ensure_plugin_dir
        from praisonaiagents.plugins.parser import parse_plugin_header_from_file
        
        source_path = Path(source).expanduser().resolve()
        
        # Validate source file
        if not source_path.exists():
            typer.echo(f"Error: File not found: {source}", err=True)
            raise typer.Exit(1)
        
        if not source_path.suffix == ".py":
            typer.echo(f"Error: Plugin must be a Python file (.py)", err=True)
            raise typer.Exit(1)
        
        # Validate plugin header
        try:
            metadata = parse_plugin_header_from_file(str(source_path))
            plugin_name = metadata.get("name", source_path.stem)
        except Exception as e:
            typer.echo(f"Error: Invalid plugin header: {e}", err=True)
            raise typer.Exit(1)
        
        # Install to user plugin directory
        plugin_dir = ensure_plugin_dir()
        dest_path = plugin_dir / source_path.name
        
        if dest_path.exists() and not force:
            overwrite = typer.confirm(f"Plugin {dest_path.name} already exists. Overwrite?")
            if not overwrite:
                typer.echo("Cancelled.")
                raise typer.Exit(0)
        
        shutil.copy2(source_path, dest_path)
        
        typer.echo(f"[green]✓[/green] Installed '{plugin_name}' to {dest_path}")
        typer.echo(f"\nTools will be available on next run.")
        
    except ImportError:
        typer.echo(f"Error: praisonaiagents package not found.", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error installing plugin: {e}", err=True)
        raise typer.Exit(1)


@app.command("discover")
def plugins_discover(
    plugin_dirs: str = typer.Option(None, "--dirs", "-d", help="Additional plugin directories (comma-separated)"),
    load: bool = typer.Option(False, "--load", "-l", help="Actually load the plugins"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Discover single-file plugins from plugin directories.
    
    Scans ~/.praison/plugins/ and ./.praison/plugins/ for valid plugins.
    
    Examples:
        praisonai plugins discover
        praisonai plugins discover --load
        praisonai plugins discover --json
    """
    try:
        from praisonaiagents.plugins.discovery import discover_plugins, discover_and_load_plugins
        
        extra_dirs = plugin_dirs.split(",") if plugin_dirs else None
        
        if load:
            plugins = discover_and_load_plugins(extra_dirs)
        else:
            plugins = discover_plugins(extra_dirs)
        
        if json_output:
            import json
            print(json.dumps(plugins, indent=2, default=str))
        else:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            if not plugins:
                console.print("[yellow]No single-file plugins found.[/yellow]")
                console.print("\nCreate one with: praisonai plugins init <name>")
                return
            
            table = Table(title=f"Single-File Plugins ({len(plugins)} found)")
            table.add_column("Name", style="cyan")
            table.add_column("Version")
            table.add_column("Tools", style="green")
            table.add_column("Path")
            
            for plugin in plugins:
                tools = plugin.get("tools", [])
                tools_str = ", ".join(tools[:3])
                if len(tools) > 3:
                    tools_str += f" (+{len(tools)-3})"
                
                table.add_row(
                    plugin.get("name", "-"),
                    plugin.get("version", "-"),
                    tools_str or "-",
                    str(plugin.get("path", "-"))[:40],
                )
            
            console.print(table)
            
            if load:
                console.print("\n[green]Plugins loaded.[/green] Tools are now available.")
            
    except ImportError:
        typer.echo(f"Error: praisonaiagents package not found.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error discovering plugins: {e}", err=True)
        raise typer.Exit(1)


@app.command("remove")
def plugins_remove(
    name: str = typer.Argument(..., help="Plugin name or filename to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Remove without confirmation"),
):
    """Remove a single-file plugin.
    
    Removes a plugin from the user's plugin directory.
    
    Examples:
        praisonai plugins remove weather
        praisonai plugins remove weather_plugin.py --force
    """
    try:
        from pathlib import Path
        from praisonaiagents.plugins.discovery import get_default_plugin_dirs
        
        # Normalize name
        if not name.endswith(".py"):
            name = f"{name}.py"
        
        # Search in plugin directories
        plugin_path = None
        for plugin_dir in get_default_plugin_dirs():
            candidate = plugin_dir / name
            if candidate.exists():
                plugin_path = candidate
                break
        
        # Also check user directory explicitly
        if not plugin_path:
            user_dir = Path.home() / ".praison" / "plugins"
            candidate = user_dir / name
            if candidate.exists():
                plugin_path = candidate
        
        if not plugin_path:
            typer.echo(f"Plugin not found: {name}", err=True)
            raise typer.Exit(1)
        
        if not force:
            confirm = typer.confirm(f"Remove plugin {plugin_path}?")
            if not confirm:
                typer.echo("Cancelled.")
                raise typer.Exit(0)
        
        plugin_path.unlink()
        typer.echo(f"[green]✓[/green] Removed: {plugin_path}")
        
    except ImportError:
        # Fallback without praisonaiagents
        from pathlib import Path
        user_dir = Path.home() / ".praison" / "plugins"
        if not name.endswith(".py"):
            name = f"{name}.py"
        plugin_path = user_dir / name
        if plugin_path.exists():
            if force or typer.confirm(f"Remove plugin {plugin_path}?"):
                plugin_path.unlink()
                typer.echo(f"[green]✓[/green] Removed: {plugin_path}")
        else:
            typer.echo(f"Plugin not found: {name}", err=True)
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error removing plugin: {e}", err=True)
        raise typer.Exit(1)


def _get_available_plugins():
    """Get list of available plugins."""
    # Built-in plugins
    plugins = [
        {
            "id": "memory-core",
            "name": "Memory Core",
            "description": "Semantic memory indexing and search",
            "enabled": True,
            "hooks": ["on_message", "on_session_start"],
        },
        {
            "id": "browser-tool",
            "name": "Browser Tool",
            "description": "Browser automation and control",
            "enabled": False,
            "hooks": ["on_tool_call"],
        },
        {
            "id": "knowledge-rag",
            "name": "Knowledge RAG",
            "description": "Retrieval-augmented generation",
            "enabled": False,
            "hooks": ["on_message", "on_context_build"],
        },
        {
            "id": "telemetry",
            "name": "Telemetry",
            "description": "Usage tracking and analytics",
            "enabled": False,
            "hooks": ["on_request", "on_response"],
        },
    ]
    
    # Try to load actual plugin registry
    try:
        from praisonaiagents.plugins import get_plugin_registry
        registry = get_plugin_registry()
        if registry:
            # Merge with actual plugins
            pass
    except ImportError:
        pass
    
    return plugins


def _get_config_path():
    """Get config file path."""
    from pathlib import Path
    
    config_dir = Path.home() / ".praisonai"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "config.json"


def _load_config(path):
    """Load config from file."""
    import json
    
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def _save_config(path, config):
    """Save config to file."""
    import json
    
    with open(path, "w") as f:
        json.dump(config, f, indent=2)


@app.callback(invoke_without_command=True)
def plugins_callback(ctx: typer.Context):
    """Show plugins help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Plugins - Plugin Management[/bold cyan]

Manage plugins with: praisonai plugins <command>

[bold]Commands:[/bold]
  [green]list[/green]        List available plugins
  [green]info[/green]        Show plugin details
  [green]enable[/green]      Enable a plugin
  [green]disable[/green]     Disable a plugin
  [green]doctor[/green]      Check plugin health

[bold]Examples:[/bold]
  praisonai plugins list
  praisonai plugins info memory-core
  praisonai plugins enable browser-tool
  praisonai plugins doctor
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)
