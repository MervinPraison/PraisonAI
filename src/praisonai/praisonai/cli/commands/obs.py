"""
Obs command group for PraisonAI CLI.

Provides observability diagnostics and management.
"""

from typing import Optional

import typer


app = typer.Typer(help="Observability diagnostics and management")


@app.command("doctor")
def obs_doctor(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Run observability health checks.

    Checks provider status, connection, and available providers.

    Examples:
        praisonai obs doctor
        praisonai obs doctor --json
    """
    try:
        from praisonai_tools.observability import obs
    except ImportError:
        from rich.console import Console
        console = Console(stderr=True)
        console.print("[red]✗ praisonai-tools not installed.[/red]")
        console.print("[dim]Install with: pip install praisonai-tools[/dim]")
        raise typer.Exit(1)

    results = obs.doctor()

    if json_output:
        import json
        typer.echo(json.dumps(results, indent=2, default=str))
        raise typer.Exit(0)

    # Pretty-print with Rich
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print("\n[bold cyan]🔍 PraisonAI Observability Doctor[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check", style="dim", min_width=20)
    table.add_column("Result")

    # Enabled
    enabled = results.get("enabled", False)
    table.add_row(
        "Enabled",
        "[green]✓ Yes[/green]" if enabled else "[yellow]✗ No[/yellow]",
    )

    # Provider
    provider = results.get("provider")
    table.add_row(
        "Active Provider",
        f"[green]{provider}[/green]" if provider else "[dim]None[/dim]",
    )

    # Connection
    conn_status = results.get("connection_status")
    conn_msg = results.get("connection_message", "")
    if conn_status is True:
        table.add_row("Connection", f"[green]✓ {conn_msg}[/green]")
    elif conn_status is False:
        table.add_row("Connection", f"[red]✗ {conn_msg}[/red]")
    else:
        table.add_row("Connection", "[dim]N/A[/dim]")

    # Available providers
    available = results.get("available_providers", [])
    table.add_row(
        "Available Providers",
        ", ".join(available) if available else "[dim]None[/dim]",
    )

    # Registered providers
    registered = results.get("registered_providers", [])
    table.add_row(
        "Registered Providers",
        ", ".join(registered) if registered else "[dim]None[/dim]",
    )

    console.print(table)
    console.print()

    raise typer.Exit(0)


@app.callback(invoke_without_command=True)
def obs_callback(ctx: typer.Context):
    """Observability diagnostics and management."""
    if ctx.invoked_subcommand is None:
        # Default to doctor when no subcommand given
        ctx.invoke(obs_doctor)
