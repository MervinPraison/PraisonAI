"""
Config command group for PraisonAI CLI.

Provides configuration management commands:
- config list: Show all configuration
- config get: Get a specific value
- config set: Set a configuration value
- config reset: Reset to defaults
"""

import json
import os
from pathlib import Path
from typing import Optional
import yaml
import typer

from ..configuration.resolver import resolve_config, get_resolver
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
    
    try:
        # Resolve configuration using new resolver
        config = resolve_config()
        config_dict = config.to_dict()
        
        if output.is_json_mode:
            output.print_json(config_dict)
            return
        
        output.print_panel("Configuration", title="PraisonAI Config")
        
        def print_dict(d, prefix=""):
            for key, value in d.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    print_dict(value, full_key)
                else:
                    output.print(f"  {full_key} = {value}")
        
        print_dict(config_dict)
        
        # Show sources if verbose
        if output.verbose:
            output.print("\n[dim]Sources:[/dim]")
            for source in config.sources:
                output.print(f"  • {source}")
    except Exception as e:
        output.print_error(f"Failed to load configuration: {e}")
        raise typer.Exit(1)


@app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Configuration key (dotted notation, e.g., output.format)"),
):
    """Get a configuration value."""
    output = get_output_controller()
    
    try:
        config = resolve_config()
        config_dict = config.to_dict()
        
        # Navigate to the key
        keys = key.split('.')
        value = config_dict
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                output.print_error(f"Key not found: {key}")
                raise typer.Exit(1)
        
        if output.is_json_mode:
            output.print_json({"key": key, "value": value})
        else:
            output.print(f"{key} = {value}")
    except Exception as e:
        output.print_error(f"Failed to get configuration: {e}")
        raise typer.Exit(1)


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
    
    # Determine which config file to update
    if scope == "user":
        config_path = Path.home() / ".praisonai" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    else:  # project
        config_path = Path.cwd() / ".praisonai" / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    
    # Load existing config
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass
    
    # Set the value
    keys = key.split('.')
    current = config
    for k in keys[:-1]:
        current = current.setdefault(k, {})
    current[keys[-1]] = parsed_value
    
    # Write back
    try:
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        config_path.chmod(0o600 if scope == "user" else 0o644)
        
        if output.is_json_mode:
            output.print_json({"key": key, "value": parsed_value, "scope": scope})
        else:
            output.print_success(f"Set {key} = {parsed_value} ({scope})")
    except Exception as e:
        output.print_error(f"Failed to save configuration: {e}")
        raise typer.Exit(1)


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
    
    # Determine which config file to reset
    if scope == "user":
        config_path = Path.home() / ".praisonai" / "config.yaml"
    else:  # project
        config_path = Path.cwd() / ".praisonai" / "config.yaml"
    
    if config_path.exists():
        config_path.unlink()
        if output.is_json_mode:
            output.print_json({"reset": True, "scope": scope, "path": str(config_path)})
        else:
            output.print_success(f"Reset {scope} configuration to defaults")
    else:
        if output.is_json_mode:
            output.print_json({"reset": False, "scope": scope, "message": "No configuration to reset"})
        else:
            output.print_info("No configuration to reset")


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
    
    if scope == "project":
        path = Path.cwd() / ".praisonai" / "config.yaml"
    else:
        path = Path.home() / ".praisonai" / "config.yaml"
    
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


@app.command("show")
def config_show(
    format: str = typer.Option(
        "yaml",
        "--format",
        "-f",
        help="Output format: yaml, json, table",
    ),
    sources: bool = typer.Option(
        False,
        "--sources",
        "-s",
        help="Show configuration sources",
    ),
):
    """Show the complete resolved configuration."""
    output = get_output_controller()
    
    try:
        config = resolve_config()
        config_dict = config.to_dict()
        
        if format == "yaml":
            yaml_output = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)
            output.print(yaml_output)
            
        elif format == "json":
            import json
            json_output = json.dumps(config_dict, indent=2)
            output.print(json_output)
            
        elif format == "table":
            def print_dict(d, prefix=""):
                for key, value in d.items():
                    full_key = f"{prefix}.{key}" if prefix else key
                    if isinstance(value, dict):
                        print_dict(value, full_key)
                    else:
                        output.print(f"  {full_key} = {value}")
            
            output.print("[bold]Configuration:[/bold]")
            print_dict(config_dict)
        
        if sources:
            output.print("\n[bold]Sources:[/bold]")
            for source in config.sources:
                output.print(f"  • {source}")
                
    except Exception as e:
        output.print_error(f"Failed to show configuration: {e}")
        raise typer.Exit(1)


@app.command("validate")
def config_validate(
    file: Optional[str] = typer.Argument(
        None,
        help="Configuration file to validate (defaults to current config)",
    ),
):
    """Validate configuration file syntax and schema."""
    output = get_output_controller()
    
    try:
        if file:
            # Validate specific file
            config_path = Path(file)
            if not config_path.exists():
                output.print_error(f"File not found: {file}")
                raise typer.Exit(1)
                
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
                
        else:
            # Validate current resolved config
            config = resolve_config()
            data = config.to_dict()
            config_path = "resolved configuration"
        
        # Check schema validity
        from ..configuration.resolver import ResolvedConfig
        
        try:
            if isinstance(data, dict):
                validated = ResolvedConfig.from_dict(data)
                output.print_success(f"✓ Configuration is valid: {config_path}")
            else:
                output.print_error(f"Configuration must be a dictionary/object: {config_path}")
                raise typer.Exit(1)
                
        except Exception as e:
            output.print_error(f"Schema validation failed: {e}")
            raise typer.Exit(1)
            
    except yaml.YAMLError as e:
        output.print_error(f"Invalid YAML syntax: {e}")
        raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Validation failed: {e}")
        raise typer.Exit(1)


@app.command("sources")
def config_sources():
    """List all configuration sources in precedence order."""
    output = get_output_controller()
    
    try:
        resolver = get_resolver()
        output.print("[bold]Configuration hierarchy:[/bold]")
        output.print("(highest precedence first)\n")
        
        # 1. CLI flags
        output.print("1. [cyan]CLI flags[/cyan] (runtime only)")
        
        # 2. Environment variables
        output.print("2. [cyan]Environment variables:[/cyan]")
        import os
        env_vars = [
            "MODEL_NAME", "OPENAI_MODEL_NAME", "PRAISONAI_MODEL",
            "PRAISONAI_PROVIDER", "OPENAI_BASE_URL", "PRAISONAI_BASE_URL",
        ]
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                output.print(f"   • {var}={value}")
        
        # 3. Project config
        output.print("3. [cyan]Project config:[/cyan]")
        project_config = resolver._load_project_config()
        if project_config and "_source" in project_config:
            output.print(f"   • {project_config['_source']} ✓")
        else:
            output.print("   • (none found)")
        
        # 4. Global config
        output.print("4. [cyan]Global config:[/cyan]")
        global_config = resolver._load_global_config()
        if global_config and "_source" in global_config:
            output.print(f"   • {global_config['_source']} ✓")
        else:
            output.print(f"   • {Path.home() / '.praisonai' / 'config.yaml'} (not found)")
        
        # 5. Built-in defaults
        output.print("5. [cyan]Built-in defaults[/cyan]")
        
    except Exception as e:
        output.print_error(f"Failed to list sources: {e}")
        raise typer.Exit(1)
