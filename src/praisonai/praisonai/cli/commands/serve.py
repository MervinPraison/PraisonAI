"""
Serve command group for PraisonAI CLI.

Provides API server management.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="API server management")


@app.command("start")
def serve_start(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    agents_file: Optional[str] = typer.Option(None, "--agents", "-a", help="Agents YAML file"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers"),
):
    """Start API server."""
    output = get_output_controller()
    
    # Build args for existing handler
    args = [
        "start",
        "--host", host,
        "--port", str(port),
        "--workers", str(workers),
    ]
    
    if agents_file:
        args.extend(["--agents", agents_file])
    if reload:
        args.append("--reload")
    
    try:
        from ..features.serve import handle_serve_command
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Serve module not available: {e}")
        raise typer.Exit(4)


@app.command("stop")
def serve_stop():
    """Stop API server."""
    output = get_output_controller()
    
    try:
        from ..features.serve import handle_serve_command
        exit_code = handle_serve_command(["stop"])
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Serve module not available: {e}")
        raise typer.Exit(4)


@app.command("status")
def serve_status(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show server status."""
    output = get_output_controller()
    
    args = ["status"]
    if json_output:
        args.append("--json")
    
    try:
        from ..features.serve import handle_serve_command
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Serve module not available: {e}")
        raise typer.Exit(4)


@app.callback(invoke_without_command=True)
def serve_callback(ctx: typer.Context):
    """Show serve help or start server."""
    if ctx.invoked_subcommand is None:
        output = get_output_controller()
        output.print_panel(
            "API server management.\n\n"
            "Commands:\n"
            "  start   Start API server\n"
            "  stop    Stop API server\n"
            "  status  Show server status\n\n"
            "Quick start:\n"
            "  praisonai serve start --agents agents.yaml",
            title="Serve Commands"
        )
