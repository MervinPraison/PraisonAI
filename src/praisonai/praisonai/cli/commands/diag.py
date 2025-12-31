"""
Diag command group for PraisonAI CLI.

Wraps existing diagnostics functionality from features/diag.py.
Provides diagnostic export for bug reports.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Diagnostics export")


@app.command("export")
def diag_export(
    output_path: Optional[str] = typer.Option(None, "--output", "-o", help="Output path"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    include_logs: bool = typer.Option(True, "--include-logs/--no-logs", help="Include log files"),
    include_config: bool = typer.Option(True, "--include-config/--no-config", help="Include configuration"),
    include_trace: bool = typer.Option(True, "--include-trace/--no-trace", help="Include recent traces"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Export diagnostic bundle for bug reports."""
    args = ["export", "--workspace", workspace]
    
    if output_path:
        args.extend(["--output", output_path])
    if not include_logs:
        args.append("--no-logs")
    if not include_config:
        args.append("--no-config")
    if not include_trace:
        args.append("--no-trace")
    if json_output:
        args.append("--json")
    
    try:
        from ..features.diag import run_diag_command
        exit_code = run_diag_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Diag module not available: {e}")
        raise typer.Exit(4)


@app.callback(invoke_without_command=True)
def diag_callback(ctx: typer.Context):
    """Show diag help or run export."""
    if ctx.invoked_subcommand is None:
        # Default to export
        diag_export()
