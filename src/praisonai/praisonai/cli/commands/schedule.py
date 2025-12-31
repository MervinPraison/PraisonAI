"""
Schedule command group for PraisonAI CLI.

Provides scheduler management.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Scheduler management")


def _run_schedule(args: list) -> int:
    """Run schedule command with args."""
    try:
        from ..features.agent_scheduler import AgentSchedulerHandler
        
        # Parse subcommand
        if args and args[0] in ['start', 'list', 'stop', 'logs', 'restart', 'delete', 'describe', 'save', 'stop-all', 'stats']:
            subcommand = args[0]
            remaining = args[1:] if len(args) > 1 else []
            
            # Create minimal args namespace
            class Args:
                pass
            
            fake_args = Args()
            return AgentSchedulerHandler.handle_daemon_command(subcommand, fake_args, remaining)
        
        return 0
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Scheduler module not available: {e}")
        return 4


@app.command("start")
def schedule_start(
    agents_file: str = typer.Argument("agents.yaml", help="Agents YAML file"),
    interval: Optional[str] = typer.Option(None, "--interval", "-i", help="Schedule interval (e.g., 'hourly', '*/30m')"),
    daemon: bool = typer.Option(True, "--daemon/--no-daemon", help="Run as daemon"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Job name"),
):
    """Start scheduled agent execution."""
    args = ["start", agents_file]
    if interval:
        args.extend(["--interval", interval])
    if not daemon:
        args.append("--no-daemon")
    if name:
        args.extend(["--name", name])
    
    raise typer.Exit(_run_schedule(args))


@app.command("stop")
def schedule_stop(
    job_id: Optional[str] = typer.Argument(None, help="Job ID to stop (or 'all')"),
):
    """Stop scheduled job(s)."""
    if job_id == "all":
        raise typer.Exit(_run_schedule(["stop-all"]))
    elif job_id:
        raise typer.Exit(_run_schedule(["stop", job_id]))
    else:
        raise typer.Exit(_run_schedule(["stop"]))


@app.command("list")
def schedule_list(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List scheduled jobs."""
    args = ["list"]
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_schedule(args))


@app.command("logs")
def schedule_logs(
    job_id: Optional[str] = typer.Argument(None, help="Job ID"),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of lines"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
):
    """View scheduler logs."""
    args = ["logs"]
    if job_id:
        args.append(job_id)
    args.extend(["--tail", str(tail)])
    if follow:
        args.append("--follow")
    raise typer.Exit(_run_schedule(args))


@app.command("restart")
def schedule_restart(
    job_id: str = typer.Argument(..., help="Job ID to restart"),
):
    """Restart a scheduled job."""
    raise typer.Exit(_run_schedule(["restart", job_id]))


@app.command("delete")
def schedule_delete(
    job_id: str = typer.Argument(..., help="Job ID to delete"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a scheduled job."""
    if not confirm:
        confirmed = typer.confirm(f"Delete job {job_id}?")
        if not confirmed:
            output = get_output_controller()
            output.print_info("Cancelled")
            raise typer.Exit(0)
    
    raise typer.Exit(_run_schedule(["delete", job_id]))


@app.command("describe")
def schedule_describe(
    job_id: str = typer.Argument(..., help="Job ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show job details."""
    args = ["describe", job_id]
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_schedule(args))


@app.command("stats")
def schedule_stats(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show scheduler statistics."""
    args = ["stats"]
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_schedule(args))


@app.callback(invoke_without_command=True)
def schedule_callback(ctx: typer.Context):
    """Show schedule help or list jobs."""
    if ctx.invoked_subcommand is None:
        schedule_list(json_output=False)
