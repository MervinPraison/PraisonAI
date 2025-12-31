"""
Config command group for PraisonAI CLI.

Provides configuration management commands:
- config list: Show all configuration
- config get: Get a specific value
- config set: Set a configuration value
- config reset: Reset to defaults
"""

from typing import Optional

import typer

from ..configuration.loader import get_config_loader
from ..output.console import get_output_controller

app = typer.Typer(help="Configuration management")


@app.command("list")
def config_list(
    scope: str = typer.Option(
        "all",
        "--scope",
        "-s",
        help="Scope to list: all, user, project",
    ),
):
    """List all configuration values."""
    output = get_output_controller()
    loader = get_config_loader()
    
    config = loader.list_all()
    
    if output.is_json_mode:
        output.print_json(config)
        return
    
    output.print_panel("Configuration", title="PraisonAI Config")
    
    def print_dict(d, prefix=""):
        for key, value in d.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                print_dict(value, full_key)
            else:
                output.print(f"  {full_key} = {value}")
    
    print_dict(config)


@app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Configuration key (dotted notation, e.g., output.format)"),
):
    """Get a configuration value."""
    output = get_output_controller()
    loader = get_config_loader()
    
    value = loader.get(key)
    
    if value is None:
        output.print_error(f"Key not found: {key}")
        raise typer.Exit(1)
    
    if output.is_json_mode:
        output.print_json({"key": key, "value": value})
    else:
        output.print(f"{key} = {value}")


@app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Configuration key (dotted notation)"),
    value: str = typer.Argument(..., help="Value to set"),
    scope: str = typer.Option(
        "user",
        "--scope",
        "-s",
        help="Scope: user or project",
    ),
):
    """Set a configuration value."""
    output = get_output_controller()
    loader = get_config_loader()
    
    # Parse value
    if value.lower() == "true":
        parsed_value = True
    elif value.lower() == "false":
        parsed_value = False
    else:
        try:
            parsed_value = int(value)
        except ValueError:
            try:
                parsed_value = float(value)
            except ValueError:
                parsed_value = value
    
    loader.set(key, parsed_value, scope=scope)
    
    if output.is_json_mode:
        output.print_json({"key": key, "value": parsed_value, "scope": scope})
    else:
        output.print_success(f"Set {key} = {parsed_value} ({scope})")


@app.command("reset")
def config_reset(
    scope: str = typer.Option(
        "user",
        "--scope",
        "-s",
        help="Scope to reset: user or project",
    ),
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation",
    ),
):
    """Reset configuration to defaults."""
    output = get_output_controller()
    
    if not confirm:
        confirmed = typer.confirm(f"Reset {scope} configuration to defaults?")
        if not confirmed:
            output.print_info("Cancelled")
            raise typer.Exit(0)
    
    loader = get_config_loader()
    loader.reset(scope=scope)
    
    if output.is_json_mode:
        output.print_json({"reset": True, "scope": scope})
    else:
        output.print_success(f"Reset {scope} configuration to defaults")


@app.command("path")
def config_path(
    scope: str = typer.Option(
        "user",
        "--scope",
        "-s",
        help="Scope: user or project",
    ),
):
    """Show configuration file path."""
    output = get_output_controller()
    
    from ..configuration.paths import get_user_config_path, get_project_config_path
    
    if scope == "project":
        path = get_project_config_path()
    else:
        path = get_user_config_path()
    
    if output.is_json_mode:
        output.print_json({"path": str(path), "exists": path.exists()})
    else:
        exists = "✓" if path.exists() else "✗"
        output.print(f"{path} [{exists}]")
