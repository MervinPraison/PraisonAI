"""
LSP command group for PraisonAI CLI.

Wraps existing LSP functionality from features/lsp_cli.py.
Provides LSP service lifecycle management.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="LSP service lifecycle management")


@app.command("start")
def lsp_start(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Language to start"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Start LSP server(s)."""
    args = ["start", "--workspace", workspace]
    if language:
        args.extend(["--language", language])
    if json_output:
        args.append("--json")
    
    try:
        from ..features.lsp_cli import run_lsp_command
        exit_code = run_lsp_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"LSP module not available: {e}")
        raise typer.Exit(4)


@app.command("stop")
def lsp_stop(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Stop LSP server(s)."""
    args = ["stop"]
    if json_output:
        args.append("--json")
    
    try:
        from ..features.lsp_cli import run_lsp_command
        exit_code = run_lsp_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"LSP module not available: {e}")
        raise typer.Exit(4)


@app.command("status")
def lsp_status(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show LSP status."""
    args = ["status", "--workspace", workspace]
    if json_output:
        args.append("--json")
    
    try:
        from ..features.lsp_cli import run_lsp_command
        exit_code = run_lsp_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"LSP module not available: {e}")
        raise typer.Exit(4)


@app.command("logs")
def lsp_logs(
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines to show"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show recent LSP logs."""
    args = ["logs", "--tail", str(tail)]
    if json_output:
        args.append("--json")
    
    try:
        from ..features.lsp_cli import run_lsp_command
        exit_code = run_lsp_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"LSP module not available: {e}")
        raise typer.Exit(4)


@app.callback(invoke_without_command=True)
def lsp_callback(ctx: typer.Context):
    """Show LSP help."""
    if ctx.invoked_subcommand is None:
        output = get_output_controller()
        output.print_panel(
            "LSP service lifecycle management.\n\n"
            "Commands:\n"
            "  start   Start LSP server(s)\n"
            "  stop    Stop LSP server(s)\n"
            "  status  Show LSP status\n"
            "  logs    Show recent logs",
            title="LSP Commands"
        )
