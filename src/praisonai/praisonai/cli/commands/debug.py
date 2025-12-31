"""
Debug command group for PraisonAI CLI.

Wraps existing debug functionality from features/debug.py.
Provides debug commands for testing interactive flows.
"""

import sys
from typing import List, Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Debug and test interactive flows")


@app.command("interactive")
def debug_interactive(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt to execute"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    lsp: bool = typer.Option(True, "--lsp/--no-lsp", help="Enable/disable LSP"),
    acp: bool = typer.Option(True, "--acp/--no-acp", help="Enable/disable ACP"),
    approval: str = typer.Option("auto", "--approval", help="Approval mode: manual, auto, scoped"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON trace"),
    trace_file: Optional[str] = typer.Option(None, "--trace-file", help="Save trace to file"),
    timeout: float = typer.Option(60.0, "--timeout", help="Timeout in seconds"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
):
    """Run single interactive turn non-interactively."""
    output = get_output_controller()
    
    # Build args for existing handler
    args = [
        "interactive",
        "--prompt", prompt,
        "--workspace", workspace,
        "--approval", approval,
        "--timeout", str(timeout),
    ]
    
    if not lsp:
        args.append("--no-lsp")
    if not acp:
        args.append("--no-acp")
    if json_output:
        args.append("--json")
    if trace_file:
        args.extend(["--trace-file", trace_file])
    if model:
        args.extend(["--model", model])
    
    # Delegate to existing handler
    try:
        from ..features.debug import run_debug_command
        exit_code = run_debug_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Debug module not available: {e}")
        raise typer.Exit(4)


@app.command("lsp")
def debug_lsp(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Language to probe"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Direct LSP probes."""
    args = ["lsp", "--workspace", workspace]
    if language:
        args.extend(["--language", language])
    if json_output:
        args.append("--json")
    
    try:
        from ..features.debug import run_debug_command
        exit_code = run_debug_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Debug module not available: {e}")
        raise typer.Exit(4)


@app.command("acp")
def debug_acp(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Direct ACP probes."""
    args = ["acp", "--workspace", workspace]
    if json_output:
        args.append("--json")
    
    try:
        from ..features.debug import run_debug_command
        exit_code = run_debug_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Debug module not available: {e}")
        raise typer.Exit(4)


@app.command("trace")
def debug_trace(
    action: str = typer.Argument("list", help="Action: record, replay, diff, list"),
    trace_id: Optional[str] = typer.Option(None, "--trace-id", "-t", help="Trace ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Trace record/replay/diff."""
    args = ["trace", action]
    if trace_id:
        args.extend(["--trace-id", trace_id])
    if json_output:
        args.append("--json")
    
    try:
        from ..features.debug import run_debug_command
        exit_code = run_debug_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Debug module not available: {e}")
        raise typer.Exit(4)


@app.callback(invoke_without_command=True)
def debug_callback(ctx: typer.Context):
    """Show debug help."""
    if ctx.invoked_subcommand is None:
        output = get_output_controller()
        output.print_panel(
            "Debug commands for testing interactive coding assistant flows.\n\n"
            "Commands:\n"
            "  interactive  Run single interactive turn\n"
            "  lsp          Direct LSP probes\n"
            "  acp          Direct ACP probes\n"
            "  trace        Trace record/replay/diff",
            title="Debug Commands"
        )
