"""
Tools command group for PraisonAI CLI.

Provides tool management commands including:
- List available tools from all sources
- Validate YAML tool references
- Show tool information
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Tool management and discovery")
console = Console()


@app.command("list")
def tools_list(
    source: Optional[str] = typer.Option(
        None, "--source", "-s", 
        help="Filter by source: builtin, local, external"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List all available tools that can be used in YAML files.
    
    Shows tools from:
    - Built-in tools (praisonaiagents.tools)
    - Local tools.py (if present)
    - External tools (praisonai-tools package)
    """
    from praisonai.tool_resolver import ToolResolver
    
    resolver = ToolResolver()
    available = resolver.list_available()
    
    if not available:
        console.print("[yellow]No tools available.[/yellow]")
        return
    
    # Categorize tools
    builtin_tools = {}
    local_tools = {}
    external_tools = {}
    
    for name, desc in available.items():
        if "Local tool" in desc:
            local_tools[name] = desc
        elif "praisonai-tools" in desc:
            external_tools[name] = desc
        else:
            builtin_tools[name] = desc
    
    # Filter by source if specified
    if source == "builtin":
        available = builtin_tools
    elif source == "local":
        available = local_tools
    elif source == "external":
        available = external_tools
    
    # Create table
    table = Table(title="Available Tools", show_header=True, header_style="bold cyan")
    table.add_column("Tool Name", style="green")
    table.add_column("Source", style="blue")
    if verbose:
        table.add_column("Description", style="dim")
    
    # Add rows
    for name in sorted(available.keys()):
        desc = available[name]
        if "Local tool" in desc:
            src = "local"
        elif "praisonai-tools" in desc:
            src = "external"
        else:
            src = "builtin"
        
        if verbose:
            table.add_row(name, src, desc[:60] + "..." if len(desc) > 60 else desc)
        else:
            table.add_row(name, src)
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(available)} tools[/dim]")
    
    if not source:
        console.print(f"[dim]  Built-in: {len(builtin_tools)} | Local: {len(local_tools)} | External: {len(external_tools)}[/dim]")


@app.command("validate")
def tools_validate(
    yaml_file: str = typer.Argument("agents.yaml", help="YAML file to validate"),
):
    """Validate that all tools in a YAML file can be resolved.
    
    Checks that every tool name in the YAML can be found in:
    - Local tools.py
    - Built-in tools (praisonaiagents.tools)
    - External tools (praisonai-tools)
    """
    import yaml
    from pathlib import Path
    from praisonai.tool_resolver import ToolResolver
    
    yaml_path = Path(yaml_file)
    if not yaml_path.exists():
        console.print(f"[red]Error: File not found: {yaml_file}[/red]")
        raise typer.Exit(1)
    
    try:
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]Error parsing YAML: {e}[/red]")
        raise typer.Exit(1)
    
    resolver = ToolResolver()
    missing = resolver.validate_yaml_tools(config)
    
    if not missing:
        console.print(f"[green]✓ All tools in {yaml_file} are valid![/green]")
        
        # Show which tools were found
        roles = config.get('roles', config.get('agents', {}))
        all_tools = set()
        for role_config in roles.values():
            if isinstance(role_config, dict):
                all_tools.update(role_config.get('tools', []))
        
        if all_tools:
            console.print(f"[dim]Tools found: {', '.join(sorted(all_tools))}[/dim]")
    else:
        console.print(f"[red]✗ Missing tools in {yaml_file}:[/red]")
        for tool in missing:
            console.print(f"  [red]• {tool}[/red]")
        
        console.print("\n[yellow]Hint: Run 'praisonai tools list' to see available tools.[/yellow]")
        raise typer.Exit(1)


@app.command("info")
def tools_info(
    name: str = typer.Argument(..., help="Tool name"),
):
    """Show detailed information about a tool."""
    from praisonai.tool_resolver import ToolResolver
    
    resolver = ToolResolver()
    tool = resolver.resolve(name)
    
    if tool is None:
        console.print(f"[red]Tool '{name}' not found.[/red]")
        console.print("[yellow]Hint: Run 'praisonai tools list' to see available tools.[/yellow]")
        raise typer.Exit(1)
    
    console.print(f"\n[bold green]{name}[/bold green]")
    console.print("-" * 40)
    
    # Get docstring
    doc = getattr(tool, '__doc__', None)
    if doc:
        console.print(f"[dim]{doc}[/dim]")
    
    # Get signature if possible
    import inspect
    try:
        sig = inspect.signature(tool)
        console.print(f"\n[cyan]Signature:[/cyan] {name}{sig}")
    except (ValueError, TypeError):
        pass
    
    # Show source
    available = resolver.list_available()
    if name in available:
        desc = available[name]
        if "Local tool" in desc:
            console.print("\n[blue]Source:[/blue] Local tools.py")
        elif "praisonai-tools" in desc:
            console.print("\n[blue]Source:[/blue] praisonai-tools package")
        else:
            console.print("\n[blue]Source:[/blue] praisonaiagents.tools (built-in)")


@app.command("test")
def tools_test(
    name: str = typer.Argument(..., help="Tool name to test"),
):
    """Test a tool with a simple invocation."""
    from praisonai.tool_resolver import ToolResolver
    
    resolver = ToolResolver()
    tool = resolver.resolve(name)
    
    if tool is None:
        console.print(f"[red]Tool '{name}' not found.[/red]")
        raise typer.Exit(1)
    
    console.print(f"[green]✓ Tool '{name}' resolved successfully![/green]")
    console.print(f"[dim]Type: {type(tool).__name__}[/dim]")
    console.print(f"[dim]Callable: {callable(tool)}[/dim]")
