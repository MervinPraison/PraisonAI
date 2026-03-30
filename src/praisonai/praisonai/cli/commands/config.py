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


@app.command("env")
def config_env(
    scope: Optional[str] = typer.Option(
        None,
        "--scope",
        "-s", 
        help="Filter by scope: core, llm, memory, tools, bots, gateway, integrations",
    ),
    validate: bool = typer.Option(
        False,
        "--validate",
        "-v",
        help="Run validation checks on current environment variables",
    ),
):
    """Show registered environment variables and their current values."""
    output = get_output_controller()
    
    try:
        from praisonaiagents.config import ConfigRegistry, ConfigScope, validate_config
    except ImportError:
        output.print_error("Unified configuration resolver not available")
        raise typer.Exit(1)
    
    if validate:
        # Run validation and show results
        validation_results = validate_config()
        
        if output.is_json_mode:
            output.print_json(validation_results)
            return
        
        output.print_panel("Configuration Validation Results", title="Environment Validation")
        
        # Show unknown variables
        if validation_results["unknown_vars"]:
            output.print("\n[bold red]Unknown PraisonAI-related environment variables:[/bold red]")
            for var in validation_results["unknown_vars"]:
                output.print(f"  • {var}")
            output.print("  Consider registering these if they're valid configuration options")
        
        # Show deprecated variables in use
        if validation_results["deprecated_vars"]:
            output.print("\n[bold yellow]Deprecated configuration in use:[/bold yellow]")
            for var in validation_results["deprecated_vars"]:
                output.print(f"  • {var}")
        
        # Show validation errors
        if validation_results["validation_errors"]:
            output.print("\n[bold red]Configuration validation errors:[/bold red]")
            for error in validation_results["validation_errors"]:
                output.print(f"  • {error}")
        
        # Summary
        total_issues = (len(validation_results["unknown_vars"]) + 
                       len(validation_results["deprecated_vars"]) + 
                       len(validation_results["validation_errors"]))
        
        if total_issues == 0:
            output.print("\n[bold green]✓ All environment variables look good![/bold green]")
        else:
            output.print(f"\n[bold yellow]Found {total_issues} configuration issues[/bold yellow]")
        
        return
    
    # Show registered environment variables
    filter_scope = None
    if scope:
        try:
            filter_scope = ConfigScope(scope.lower())
        except ValueError:
            output.print_error(f"Invalid scope: {scope}. Valid scopes: {', '.join(ConfigScope)}")
            raise typer.Exit(1)
    
    entries = ConfigRegistry.list_entries(scope=filter_scope)
    
    if output.is_json_mode:
        env_data = []
        for entry in entries:
            import os
            current_value = os.getenv(entry.env_var)
            env_data.append({
                "key": entry.key,
                "env_var": entry.env_var,
                "scope": entry.scope.value,
                "type": entry.type.value,
                "description": entry.description,
                "default": entry.default,
                "current_value": current_value,
                "is_set": current_value is not None,
                "deprecated": entry.deprecated,
                "aliases": entry.aliases,
            })
        output.print_json(env_data)
        return
    
    scope_title = f" - {filter_scope.value.title()}" if filter_scope else ""
    output.print_panel(f"Environment Variables{scope_title}", title="PraisonAI Configuration")
    
    if not entries:
        output.print("No registered environment variables found.")
        return
    
    # Group by scope
    by_scope = {}
    for entry in entries:
        scope_name = entry.scope.value
        if scope_name not in by_scope:
            by_scope[scope_name] = []
        by_scope[scope_name].append(entry)
    
    import os
    
    for scope_name, scope_entries in by_scope.items():
        output.print(f"\n[bold cyan]{scope_name.upper()}[/bold cyan]")
        
        for entry in scope_entries:
            current_value = os.getenv(entry.env_var)
            is_set = current_value is not None
            
            # Status indicator
            status = "✓" if is_set else "○"
            status_color = "green" if is_set else "dim"
            
            # Entry display
            deprecated_marker = " [bold red](deprecated)[/bold red]" if entry.deprecated else ""
            aliases_text = f" (aliases: {', '.join(entry.aliases)})" if entry.aliases else ""
            
            output.print(f"  [{status_color}]{status}[/{status_color}] {entry.env_var}{deprecated_marker}")
            output.print(f"      {entry.description}{aliases_text}")
            
            if is_set:
                # Mask sensitive values (API keys, tokens)
                if any(sensitive in entry.env_var.lower() for sensitive in ['key', 'token', 'secret', 'password']):
                    masked_value = f"{current_value[:8]}..." if len(current_value) > 8 else "***"
                    output.print(f"      Current: [dim]{masked_value}[/dim]")
                else:
                    output.print(f"      Current: [dim]{current_value}[/dim]")
            elif entry.default is not None:
                output.print(f"      Default: [dim]{entry.default}[/dim]")
            
            output.print(f"      Type: [dim]{entry.type.value}[/dim]")


@app.command("doctor")
def config_doctor():
    """Run comprehensive configuration diagnostics."""
    output = get_output_controller()
    
    try:
        from praisonaiagents.config import validate_config, ConfigRegistry
    except ImportError:
        output.print_error("Unified configuration resolver not available")
        raise typer.Exit(1)
    
    output.print_panel("Configuration Doctor", title="Diagnosing PraisonAI Configuration")
    
    validation_results = validate_config()
    
    # Count registered configs
    total_registered = len(ConfigRegistry._entries)
    output.print(f"[bold cyan]Registered environment variables:[/bold cyan] {total_registered}")
    
    # Environment variable analysis
    import os
    all_env_vars = len(os.environ)
    praison_vars = len([var for var in os.environ if 'PRAISON' in var])
    llm_vars = len([var for var in os.environ if any(provider in var for provider in ['OPENAI', 'ANTHROPIC', 'GOOGLE', 'GEMINI', 'CLAUDE'])])
    
    output.print(f"[bold cyan]Total environment variables:[/bold cyan] {all_env_vars}")
    output.print(f"[bold cyan]PraisonAI variables:[/bold cyan] {praison_vars}")
    output.print(f"[bold cyan]LLM provider variables:[/bold cyan] {llm_vars}")
    
    # Issues summary
    total_issues = (len(validation_results["unknown_vars"]) + 
                   len(validation_results["deprecated_vars"]) + 
                   len(validation_results["validation_errors"]))
    
    if total_issues == 0:
        output.print("\n[bold green]✓ Configuration looks healthy![/bold green]")
    else:
        output.print(f"\n[bold yellow]⚠ Found {total_issues} configuration issues[/bold yellow]")
        
        if validation_results["unknown_vars"]:
            output.print(f"  • {len(validation_results['unknown_vars'])} unknown variables")
        
        if validation_results["deprecated_vars"]:
            output.print(f"  • {len(validation_results['deprecated_vars'])} deprecated variables in use")
        
        if validation_results["validation_errors"]:
            output.print(f"  • {len(validation_results['validation_errors'])} validation errors")
        
        output.print("\nRun 'praison config env --validate' for detailed information")
    
    # Performance check
    from praisonaiagents.config.resolver import ConfigRegistry
    cache_size = len(ConfigRegistry._provider._cache) if ConfigRegistry._provider._cache_enabled else 0
    cache_status = "enabled" if ConfigRegistry._provider._cache_enabled else "disabled"
    
    output.print(f"\n[bold cyan]Configuration cache:[/bold cyan] {cache_status} ({cache_size} entries)")
    
    if output.is_json_mode:
        output.print_json({
            "total_registered": total_registered,
            "total_env_vars": all_env_vars,
            "praison_vars": praison_vars,
            "llm_vars": llm_vars,
            "issues": {
                "total": total_issues,
                "unknown_vars": len(validation_results["unknown_vars"]),
                "deprecated_vars": len(validation_results["deprecated_vars"]),
                "validation_errors": len(validation_results["validation_errors"]),
            },
            "cache": {
                "enabled": ConfigRegistry._provider._cache_enabled,
                "size": cache_size,
            }
        })
