"""
Command management for custom command definitions.

Provides commands to list and inspect custom command definitions.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Manage custom commands")


@app.command(name="list")
def list_commands(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    all_sources: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="List the full interactive command namespace (built-ins, custom, skills, MCP)",
    ),
):
    """List all discovered custom commands.

    By default only custom ``.praisonai/commands/*.md`` commands are shown.
    Pass ``--all`` to list the same unified namespace the interactive session
    resolves ``/name`` from, so listing and invocation cannot drift.
    """
    output = get_output_controller()

    if all_sources:
        return _list_registry(output)

    try:
        from praisonai_code.cli.features.custom_definitions import CustomDefinitionsDiscovery
        
        discovery = CustomDefinitionsDiscovery()
        discovery.discover()
        
        commands = discovery.list_commands()
        
        if not commands:
            output.print_info("No custom commands found.")
            output.print_info("Run 'praisonai init' to scaffold a starter .praisonai/ project,")
            output.print_info("or create commands in .praisonai/commands/*.md or ~/.praisonai/commands/*.md")
            return
        
        from rich.table import Table
        from rich.console import Console
        
        console = Console()
        table = Table(title="Custom Commands", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="yellow")
        table.add_column("Description", style="green")
        
        if verbose:
            table.add_column("Path", style="dim")
        
        for cmd in commands:
            row = [
                cmd.name,
                cmd.source,
                cmd.description or "No description",
            ]
            
            if verbose:
                row.append(str(cmd.path))
            
            table.add_row(*row)
        
        console.print(table)
        
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def show(
    name: str = typer.Argument(help="Command name to inspect"),
    preview: bool = typer.Option(False, "--preview", "-p", help="Preview with sample arguments"),
):
    """Show details of a specific command."""
    output = get_output_controller()
    
    try:
        from praisonai_code.cli.features.custom_definitions import CustomDefinitionsDiscovery, TemplateInterpolator
        
        discovery = CustomDefinitionsDiscovery()
        cmd = discovery.get_command(name)
        
        if not cmd:
            output.print_error(f"Command '{name}' not found")
            raise typer.Exit(1)
        
        from rich.console import Console
        from rich.panel import Panel
        from rich.syntax import Syntax
        
        console = Console()
        
        # Build command info
        info = f"""[bold cyan]Command: {cmd.name}[/bold cyan]
[yellow]Source:[/yellow] {cmd.source}
[yellow]Path:[/yellow] {cmd.path}
[yellow]Description:[/yellow] {cmd.description or 'No description'}"""
        
        console.print(Panel(info, title="Command Details", border_style="cyan"))
        
        # Show template
        syntax = Syntax(cmd.template, "markdown", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, title="Template", border_style="green"))
        
        # Show preview if requested
        if preview:
            interpolator = TemplateInterpolator()
            sample_args = "<sample arguments>"
            preview_text = interpolator.interpolate(cmd.template, sample_args)
            syntax = Syntax(preview_text, "markdown", theme="monokai", line_numbers=False)
            console.print(Panel(syntax, title=f"Preview with args: '{sample_args}'", border_style="yellow"))
    
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


def _list_registry(output) -> None:
    """List the full unified command namespace via ``CommandRegistry``.

    This is the same registry every interactive surface drives ``/name``
    resolution and ``/help`` from, so what is listed here is exactly what can
    be invoked interactively.
    """
    try:
        from praisonai_code.cli.interactive.command_registry import (
            create_default_registry,
        )

        try:
            from praisonai_code.cli.interactive.repl import DEFAULT_COMMANDS as builtins
        except Exception:  # pragma: no cover - defensive
            builtins = None

        registry = create_default_registry(
            builtins,
            include_custom=True,
            include_skills=True,
        )
        commands = registry.list_commands()

        if not commands:
            output.print_info("No commands found.")
            return

        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Commands", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Kind", style="magenta")
        table.add_column("Source", style="yellow")
        table.add_column("Description", style="green")

        for cmd in commands:
            table.add_row(
                cmd.name,
                cmd.kind.value,
                cmd.source,
                cmd.description or "No description",
            )

        console.print(table)

    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)