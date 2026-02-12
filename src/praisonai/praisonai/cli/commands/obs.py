"""
Obs command group for PraisonAI CLI.

Thin wrapper that re-exports the CLI from praisonai_tools.
"""

try:
    from praisonai_tools.observability.cli import app
except ImportError:
    import typer
    app = typer.Typer(help="Observability diagnostics and management")

    @app.callback(invoke_without_command=True)
    def obs_fallback(ctx: typer.Context):
        """Observability diagnostics and management."""
        from rich.console import Console
        Console(stderr=True).print("[red]✗ praisonai-tools not installed.[/red]")
        Console(stderr=True).print("[dim]Install with: pip install praisonai-tools[/dim]")
        raise typer.Exit(1)
