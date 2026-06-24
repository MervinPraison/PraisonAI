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


@app.command("add")
def schedule_add_cmd(
    name: str = typer.Argument(..., help="Schedule name (e.g. 'morning-hello')"),
    schedule: str = typer.Option(..., "--schedule", "-s", help="When to run: 'hourly', 'daily', '*/30m', 'cron:0 9 * * *', 'at:2026-03-01T09:00', 'in 20 minutes'"),
    message: str = typer.Option("", "--message", "-m", help="Prompt / reminder text"),
    agent: str = typer.Option("", "--agent", "-a", help="Agent ID to execute this job (default: first registered agent)"),
    deliver: str = typer.Option("", "--deliver", "-d", help="Delivery token: 'origin', 'telegram', 'all', or 'platform:chat_id[:thread_id]'"),
    channel: str = typer.Option("", "--channel", help="[Legacy] Delivery platform: telegram, discord, slack, whatsapp"),
    channel_id: str = typer.Option("", "--channel-id", help="[Legacy] Target chat/channel ID on the platform"),
    session_id: str = typer.Option("", "--session-id", help="Session ID to preserve conversation context"),
    pre_run: str = typer.Option("", "--pre-run", help="Cheap pre-run gate command: exit 0 + output => run (output seeds the prompt); non-zero => skip (no model tokens, no delivery)"),
    condition: str = typer.Option("", "--condition", help="Natural-language / expression alias for the pre-run gate"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Add a job to the schedule store (with optional delivery target).

    Examples:
        praisonai schedule add "morning-hello" -s "cron:0 9 * * *" -m "say hello"
        praisonai schedule add "news" -s daily -m "news summary" --deliver telegram
        praisonai schedule add "report" -s hourly -m "status report" --deliver all
        praisonai schedule add "tg-reminder" -s daily -m "check email" --agent support --channel telegram --channel-id 12345
        praisonai schedule add "inbox-watch" -s "*/5m" -m "Summarise new emails" --pre-run "scripts/new_mail.sh" --deliver telegram
    """
    output = get_output_controller()
    try:
        from praisonaiagents.tools.schedule_tools import schedule_add as _schedule_add

        # Build delivery target based on new or legacy format
        delivery_kwargs = {}
        if deliver:
            # New token-based delivery
            delivery_kwargs["deliver"] = deliver
        elif channel or channel_id:
            # Legacy explicit channel/channel_id
            delivery_kwargs["channel"] = channel
            delivery_kwargs["channel_id"] = channel_id
        
        if session_id:
            delivery_kwargs["session_id"] = session_id
        
        result = _schedule_add(
            name=name,
            schedule=schedule,
            message=message,
            agent_id=agent,
            pre_run=pre_run,
            condition=condition,
            **delivery_kwargs
        )

        if json_output:
            import json as _json
            print(_json.dumps({"result": result}))
        else:
            if "Error" in result:
                output.print_error(result)
                raise typer.Exit(1)
            else:
                output.print_success(result)
    except ImportError as e:
        output.print_error(f"Schedule tools not available: {e}")
        raise typer.Exit(4)


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
