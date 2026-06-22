"""
YAML configuration validation command.

Validates agents/tasks/workflow YAML configurations with comprehensive error checking.
"""

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="Validate YAML configuration files",
    no_args_is_help=True
)

console = Console()


@app.command()
def validate(
    file: str = typer.Argument(
        ...,
        help="Path to YAML configuration file to validate"
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat warnings as errors (strict validation mode)"
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet", "-q",
        help="Only show errors, suppress success messages"
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output validation results as JSON"
    ),
):
    """
    Validate a YAML configuration file for agents, tasks, and workflows.
    
    This command performs comprehensive validation including:
    - Schema validation for required and optional fields
    - Type checking for all configuration values
    - Cross-reference validation (tasks -> agents, tools -> definitions)
    - Detection of unknown fields with suggestions
    
    Examples:
        praisonai validate agents.yaml
        praisonai validate agents.yaml --strict
        praisonai validate my-config.yaml --json
    """
    from ...config.validator import ConfigValidator
    import json as json_module
    
    file_path = Path(file)
    
    # Handle JSON output for missing file
    if not file_path.exists():
        if json_output:
            output = {
                "file": str(file_path),
                "valid": False,
                "errors": [f"File not found: {file}"],
                "warnings": [],
                "strict_mode": strict
            }
            sys.stdout.write(json_module.dumps(output, indent=2) + "\n")
        else:
            console.print(f"[red]✗ File not found:[/red] {file}", style="bold")
        sys.exit(1)
    
    # Initialize validator
    validator = ConfigValidator()
    
    # Validate the file
    result = validator.validate_yaml_file(str(file_path), strict=strict)
    
    # Output JSON if requested
    if json_output:
        output = {
            "file": str(file_path),
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "strict_mode": strict
        }
        sys.stdout.write(json_module.dumps(output, indent=2) + "\n")
        sys.exit(0 if result.valid else 1)
    
    # Display results
    if result.valid:
        if not quiet:
            console.print(f"[green]✓ Configuration is valid[/green]: {file_path}", style="bold")
            
            if result.warnings:
                console.print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
                for i, warning in enumerate(result.warnings, 1):
                    console.print(f"  {i}. {warning}")
        sys.exit(0)
    else:
        console.print(f"[red]✗ Configuration validation failed[/red]: {file_path}", style="bold")
        
        if result.errors:
            console.print(f"\n[red]Errors ({len(result.errors)}):[/red]")
            for i, error in enumerate(result.errors, 1):
                console.print(f"  {i}. {error}")
        
        if result.warnings and not strict:
            console.print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
            for i, warning in enumerate(result.warnings, 1):
                console.print(f"  {i}. {warning}")
        
        if not quiet:
            console.print(f"\n[dim]Fix the errors above and run validation again.[/dim]")
            if result.warnings and not strict:
                console.print("[dim]Use --strict to treat warnings as errors.[/dim]")
        
        sys.exit(1)


@app.command()
def check(
    directory: str = typer.Argument(
        ".",
        help="Directory to search for YAML files"
    ),
    pattern: str = typer.Option(
        "*.yaml",
        "--pattern", "-p",
        help="Glob pattern for YAML files"
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat warnings as errors"
    ),
    stop_on_error: bool = typer.Option(
        False,
        "--stop-on-error",
        help="Stop checking files after first error"
    ),
):
    """
    Check all YAML configuration files in a directory.
    
    Examples:
        praisonai validate check .
        praisonai validate check ./configs --pattern "*.yml"
        praisonai validate check . --strict --stop-on-error
    """
    from ...config.validator import ConfigValidator
    import glob
    
    # Find all matching files
    dir_path = Path(directory)
    if not dir_path.exists():
        console.print(f"[red]✗ Directory not found:[/red] {directory}", style="bold")
        sys.exit(1)
    
    # Find files matching pattern
    yaml_files = list(dir_path.glob(pattern))
    if pattern == "*.yaml":
        yaml_files.extend(dir_path.glob("*.yml"))
    
    if not yaml_files:
        console.print(f"[yellow]No YAML files found matching pattern:[/yellow] {pattern}")
        sys.exit(0)
    
    # Initialize validator
    validator = ConfigValidator()
    
    # Create results table
    table = Table(title=f"Validation Results for {len(yaml_files)} file(s)")
    table.add_column("File", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Errors", justify="center")
    table.add_column("Warnings", justify="center")
    
    total_valid = 0
    total_invalid = 0
    total_errors = 0
    total_warnings = 0
    
    for yaml_file in sorted(yaml_files):
        result = validator.validate_yaml_file(str(yaml_file), strict=strict)
        
        if result.valid:
            status = "[green]✓ Valid[/green]"
            total_valid += 1
        else:
            status = "[red]✗ Invalid[/red]"
            total_invalid += 1
            
            if stop_on_error:
                console.print(f"\n[red]Validation failed for:[/red] {yaml_file}")
                console.print(result.format_message())
                sys.exit(1)
        
        total_errors += len(result.errors)
        total_warnings += len(result.warnings)
        
        table.add_row(
            str(yaml_file.relative_to(dir_path)),
            status,
            str(len(result.errors)) if result.errors else "-",
            str(len(result.warnings)) if result.warnings else "-"
        )
    
    # Display results
    console.print(table)
    
    # Summary
    console.print(f"\nSummary:")
    console.print(f"  Valid files: [green]{total_valid}[/green]")
    console.print(f"  Invalid files: [red]{total_invalid}[/red]")
    console.print(f"  Total errors: {total_errors}")
    console.print(f"  Total warnings: {total_warnings}")
    
    sys.exit(0 if total_invalid == 0 else 1)


@app.command()
def schema():
    """
    Display the YAML configuration schema documentation.
    
    Shows all available fields, their types, and descriptions for:
    - Agent/Role configuration
    - Task configuration  
    - Workflow configuration
    - Global settings
    """
    from ...config.schema import YAMLConfig, AgentConfig, TaskConfig
    import json
    
    console.print("[bold cyan]PraisonAI YAML Configuration Schema[/bold cyan]\n")
    
    # Display main sections
    console.print("[bold]Main Configuration Sections:[/bold]")
    console.print("  • roles/agents - Define agent roles and capabilities")
    console.print("  • tasks - Define tasks and their assignments")
    console.print("  • workflow - Configure workflow execution")
    console.print("  • tools/toolsets - Global tool configuration")
    console.print("  • config - Global settings (acp, lsp)")
    console.print()
    
    # Display agent fields
    console.print("[bold]Agent/Role Fields:[/bold]")
    agent_schema = AgentConfig.model_json_schema()
    required_fields = agent_schema.get('required', [])
    
    for field_name, field_info in agent_schema.get('properties', {}).items():
        required = " [red](required)[/red]" if field_name in required_fields else ""
        description = field_info.get('description', 'No description')
        field_type = field_info.get('type', 'any')
        
        # Handle complex types
        if 'anyOf' in field_info:
            types = [t.get('type', 'object') for t in field_info['anyOf'] if 'type' in t]
            field_type = ' | '.join(types) if types else 'mixed'
        elif '$ref' in field_info:
            field_type = field_info['$ref'].split('/')[-1]
        
        console.print(f"  • {field_name}{required} ({field_type}): {description}")
    
    console.print()
    
    # Display task fields
    console.print("[bold]Task Fields:[/bold]")
    task_schema = TaskConfig.model_json_schema()
    required_fields = task_schema.get('required', [])
    
    for field_name, field_info in task_schema.get('properties', {}).items():
        required = " [red](required)[/red]" if field_name in required_fields else ""
        description = field_info.get('description', 'No description')
        field_type = field_info.get('type', 'any')
        console.print(f"  • {field_name}{required} ({field_type}): {description}")
    
    console.print()
    console.print("[dim]Use 'praisonai validate <file>' to validate your configuration.[/dim]")


if __name__ == "__main__":
    app()