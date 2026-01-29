"""
ACP command group for PraisonAI CLI.

Wraps existing ACP functionality from features/acp.py.
Provides Agent Client Protocol server for IDE integration.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Agent Client Protocol server")


@app.callback(invoke_without_command=True)
def acp_main(
    ctx: typer.Context,
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    agent: str = typer.Option("default", "--agent", "-a", help="Agent name or configuration file"),
    agents_file: Optional[str] = typer.Option(None, "--agents", help="Multi-agent configuration YAML file"),
    router: bool = typer.Option(False, "--router", help="Enable router agent for task delegation"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    resume: Optional[str] = typer.Option(None, "--resume", "-r", help="Resume session by ID"),
    last: bool = typer.Option(False, "--last", help="Resume the last session"),
    approve: str = typer.Option("manual", "--approve", help="Approval mode: manual, auto, scoped"),
    read_only: bool = typer.Option(True, "--read-only/--allow-write", help="Read-only mode"),
    allow_shell: bool = typer.Option(False, "--allow-shell", help="Allow shell command execution"),
    allow_network: bool = typer.Option(False, "--allow-network", help="Allow network requests"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    profile: Optional[str] = typer.Option(None, "--profile", help="Use named profile from config"),
):
    """Start ACP server for IDE integration.
    
    DEPRECATED: Use `praisonai serve acp` instead.
    """
    import sys
    
    # Print deprecation warning
    print("\n\033[93m⚠ DEPRECATION WARNING:\033[0m", file=sys.stderr)
    print("\033[93m'praisonai acp' is deprecated and will be removed in a future version.\033[0m", file=sys.stderr)
    print("\033[93mPlease use 'praisonai serve acp' instead.\033[0m\n", file=sys.stderr)
    
    # Build args for existing handler
    args = [
        "--workspace", workspace,
        "--agent", agent,
        "--approve", approve,
    ]
    
    if agents_file:
        args.extend(["--agents", agents_file])
    if router:
        args.append("--router")
    if model:
        args.extend(["--model", model])
    if resume:
        args.extend(["--resume", resume])
    if last:
        args.append("--last")
    if not read_only:
        args.append("--allow-write")
    if allow_shell:
        args.append("--allow-shell")
    if allow_network:
        args.append("--allow-network")
    if debug:
        args.append("--debug")
    if profile:
        args.extend(["--profile", profile])
    
    try:
        from ..features.acp import run_acp_command
        exit_code = run_acp_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"ACP module not available: {e}")
        raise typer.Exit(4)
