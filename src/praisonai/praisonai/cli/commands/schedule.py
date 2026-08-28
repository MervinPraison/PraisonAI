"""
Schedule command group for PraisonAI CLI.

Provides scheduler management.
"""

import math
import re
from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Scheduler management")


def _run_schedule(args: list) -> int:
    """Run schedule command with args."""
    try:
        from praisonai.cli.features.agent_scheduler import AgentSchedulerHandler
        
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
    tz: str = typer.Option("", "--tz", help="IANA timezone for cron or naive one-shot times (e.g. America/New_York)"),
    message: str = typer.Option("", "--message", "-m", help="Prompt / reminder text"),
    agent: str = typer.Option("", "--agent", "-a", help="Agent ID to execute this job (default: first registered agent)"),
    deliver: str = typer.Option("", "--deliver", "-d", help="Delivery token: 'origin', 'telegram', 'all', or 'platform:chat_id[:thread_id]'"),
    channel: str = typer.Option("", "--channel", help="[Legacy] Delivery platform: telegram, discord, slack, whatsapp"),
    channel_id: str = typer.Option("", "--channel-id", help="[Legacy] Target chat/channel ID on the platform"),
    session_id: str = typer.Option("", "--session-id", help="Session ID to preserve conversation context"),
    continuable: bool = typer.Option(True, "--continuable/--no-continuable", help="Seed a resumable session on delivery so a reply resumes the job with context (default); --no-continuable for fire-and-forget notices"),
    pre_run: str = typer.Option("", "--pre-run", help="Cheap pre-run gate command: exit 0 + output => run (output seeds the prompt); non-zero => skip (no model tokens, no delivery)"),
    condition: str = typer.Option("", "--condition", help="Natural-language / expression alias for the pre-run gate"),
    monitor_command: str = typer.Option("", "--monitor-command", help="Run the agent only when this command's stdout changes"),
    monitor_url: str = typer.Option("", "--monitor-url", help="Run the agent only when this public HTTP(S) response changes"),
    command: str = typer.Option("", "--command", "--script", help="No-LLM action: run this shell command on schedule and deliver its stdout verbatim (no agent, no model turn)"),
    command_timeout: float = typer.Option(60.0, "--command-timeout", help="Max seconds the --command may run before it is killed (default 60)"),
    backend: str = typer.Option("", "--backend", help="External coding-CLI backend action: run the message as one headless turn via a registered backend (see 'praisonai backends'), e.g. claude-code, codex-cli. No native agent, no in-process model turn"),
    backend_cwd: str = typer.Option("", "--backend-cwd", help="Working directory for the --backend turn (default: the scheduler process cwd)"),
    backend_timeout: float = typer.Option(0.0, "--backend-timeout", help="Max seconds the --backend turn may run (default: the backend's own timeout, 300s)"),
    model: str = typer.Option("", "--model", help="Pin this job to a specific model (e.g. 'openai/gpt-4o-mini'). Snapshotted so unattended runs stay stable and drift fails closed. Pass an explicit model to capture a snapshot"),
    pin: bool = typer.Option(True, "--pin/--no-pin", help="Enforce the model snapshot so drift fails closed (default; only takes effect once a snapshot exists via --model). --no-pin follows whatever the default becomes"),
    once: bool = typer.Option(False, "--once", help="One-shot job: auto-remove after its single fire (maps to delete_after_run). Ideal for 'at:'/'in ...' reminders"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Add a job to the schedule store (with optional delivery target).

    Examples:
        praisonai schedule add "morning-hello" -s "cron:0 9 * * *" -m "say hello"
        praisonai schedule add "morning-brief" -s "cron:0 8 * * *" --tz America/New_York -m "summarise activity"
        praisonai schedule add "news" -s daily -m "news summary" --deliver telegram
        praisonai schedule add "report" -s hourly -m "status report" --deliver all
        praisonai schedule add "tg-reminder" -s daily -m "check email" --agent support --channel telegram --channel-id 12345
        praisonai schedule add "inbox-watch" -s "*/5m" -m "Summarise new emails" --pre-run "scripts/new_mail.sh" --deliver telegram
        praisonai schedule add "price-watch" -s "*/15m" -m "Summarise the change" --monitor-url "https://example.com/api/price" --deliver telegram
        praisonai schedule add "disk-watch" -s hourly --command "df -h /" --deliver telegram:-100123
        praisonai schedule add "nightly-refactor" -s "cron:0 2 * * *" -m "tidy utils.py, run tests" --backend claude-code --backend-cwd ~/proj --deliver telegram
    """
    output = get_output_controller()
    if (
        backend
        and isinstance(backend_timeout, (int, float))
        and backend_timeout
        and not (math.isfinite(backend_timeout) and backend_timeout >= 0)
    ):
        output.print_error(
            "--backend-timeout must be a finite, non-negative number of seconds."
        )
        raise typer.Exit(1)
    if command and backend:
        output.print_error(
            "--command and --backend are mutually exclusive: a job runs exactly "
            "one model-free action. Configure one or the other."
        )
        raise typer.Exit(1)
    if monitor_command and monitor_url:
        output.print_error(
            "--monitor-command and --monitor-url are mutually exclusive."
        )
        raise typer.Exit(1)
    if (monitor_command or monitor_url) and (pre_run or command or backend):
        output.print_error(
            "Monitor options cannot be combined with --pre-run, --command, "
            "or --backend."
        )
        raise typer.Exit(1)
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

        # Opt-out only: True is the default, so pass it through solely when a
        # delivery target exists and the user asked for fire-and-forget.
        if delivery_kwargs and not continuable:
            delivery_kwargs["continuable"] = False

        result = _schedule_add(
            name=name,
            schedule=schedule,
            tz=tz,
            message=message,
            agent_id=agent,
            once=once,
            **delivery_kwargs
        )

        # ``pre_run``/``monitor``/``condition``/``command``/``backend`` run an arbitrary
        # host process, so they are NOT part of the LLM-callable schedule_add
        # surface. The CLI is a trusted, human-driven surface, so set them on
        # the stored job here. A ``--command`` job runs verbatim with no agent
        # and no model turn, delivering its stdout to the delivery target.
        # ``--model``/``--no-pin`` snapshot the model/pin policy onto the job so
        # an unattended run stays pinned and drift fails closed. A model-free
        # ``--command`` job takes no model turn, so pinning is skipped for it.
        # Only apply trusted post-add options when THIS invocation actually
        # created the job. A duplicate-name response ("already exists") is a
        # rejection: mutating the existing job here would let a rejected add
        # reconfigure a live schedule (e.g. attach a new --command/--backend).
        success_prefix = f"Schedule '{name}' added (id: "
        job_id_match = re.match(
            rf"^{re.escape(success_prefix)}([^,\s)]+)(?:,|\))", result,
        )
        job_created = job_id_match is not None
        want_pin_update = bool(model) or (not pin and not command)
        if (
            pre_run
            or condition
            or monitor_command
            or monitor_url
            or command
            or backend
            or want_pin_update
        ) and job_created:
            try:
                from praisonaiagents.tools.schedule_tools import _get_store
                store = _get_store()
                if job_id_match is None:
                    raise ValueError("schedule_add success response omitted the job id")
                job = store.get(job_id_match.group(1))
                if job is not None:
                    job.pre_run = pre_run or None
                    job.condition = condition or None
                    if monitor_command:
                        job.monitor = {"command": monitor_command}
                    elif monitor_url:
                        job.monitor = {"url": monitor_url}
                    job.command = command or None
                    if command:
                        job.command_timeout = command_timeout
                    if backend:
                        job.backend = backend
                        backend_options = {}
                        if backend_cwd:
                            backend_options["cwd"] = backend_cwd
                        if backend_timeout and backend_timeout > 0:
                            # Round up so a positive sub-millisecond value stays
                            # positive instead of collapsing to 0 (which the
                            # executor would replace with the 300s default).
                            backend_options["timeout_ms"] = max(
                                1, round(backend_timeout * 1000)
                            )
                        job.backend_options = backend_options
                        # A backend turn uses the pinned model as an input
                        # (passed to the CLI), not as a drift guard.
                        if model:
                            job.model = model
                    if not command:
                        if model:
                            job.model = model
                        job.pin_model = pin
                    store.update(job)
            except Exception as e:
                output.print_error(f"Failed to set trusted schedule options: {e}")
                raise typer.Exit(1)

        # A rejected add (duplicate name or error) must exit non-zero so
        # scripts/CI never treat it as success. Detect failure as the absence
        # of the producer-owned success confirmation rather than substring
        # matching on error words — a schedule *named* "Error monitor" or
        # "already exists" appears inside the success message and must not be
        # misclassified as a failure.
        add_failed = not job_created
        if json_output:
            import json as _json
            print(_json.dumps({"result": result}))
            if add_failed:
                raise typer.Exit(1)
        else:
            if add_failed:
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


@app.command("run")
def schedule_run(
    poll: float = typer.Option(15.0, "--poll", "-p", help="Seconds between store polls (default 15)"),
):
    """Poll and fire store-backed jobs in the foreground (Ctrl-C to stop).

    Hosts the store poller standalone — without the messaging gateway or UI
    host — so a job added via ``praisonai schedule add`` actually runs. Firing
    is lease-safe (``claim_due_jobs``), so this never double-fires alongside a
    running gateway.

    Examples:
        praisonai schedule add "brief" -s daily -m "morning brief" --deliver telegram
        praisonai schedule run
    """
    output = get_output_controller()
    try:
        from praisonaiagents.scheduler import get_default_store, ScheduleLoop
        from praisonai.integration.bridges.schedules_runner import _build_executor
    except ImportError as e:
        output.print_error(f"Scheduler module not available: {e}")
        raise typer.Exit(4)

    store = get_default_store()
    executor = _build_executor(store)
    if executor is None:
        output.print_error(
            "Schedule executor unavailable; cannot run the poller. "
            "Install the bot extras (praisonai_bot) to execute scheduled jobs."
        )
        raise typer.Exit(4)

    from praisonai._async_bridge import run_sync_or_offload

    def on_trigger(job):
        run_sync_or_offload(
            executor._execute_one(job),
            timeout=None,
            thread_name="praisonai-schedule-run",
        )

    loop = ScheduleLoop(on_trigger=on_trigger, store=store)
    output.print_info(
        f"Polling store schedules every {poll:g}s (Ctrl-C to stop)…"
    )
    try:
        loop.run_forever(poll_seconds=poll)
    except KeyboardInterrupt:
        pass
    output.print_info("Scheduler stopped.")


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


def _fmt_schedule(sched) -> str:
    """Render a Schedule to a short human string."""
    try:
        if sched.kind == "every" and sched.every_seconds:
            secs = sched.every_seconds
            if secs >= 86400 and secs % 86400 == 0:
                return f"every {secs // 86400}d"
            if secs >= 3600 and secs % 3600 == 0:
                return f"every {secs // 3600}h"
            if secs >= 60 and secs % 60 == 0:
                return f"every {secs // 60}m"
            return f"every {secs}s"
        if sched.kind == "cron":
            return f"cron: {sched.cron_expr}"
        if sched.kind == "at":
            return f"at: {sched.at}"
        return str(sched.kind)
    except Exception:
        return "?"


def _fmt_ts(ts) -> str:
    """Render an epoch timestamp as a short local string, or '-'."""
    if not ts:
        return "-"
    try:
        import datetime as _dt
        return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def _store_jobs_payload(jobs) -> list:
    """Serialise store-backed ScheduleJobs to plain dicts for JSON output."""
    return [{
        "source": "store",
        "id": j.id,
        "name": j.name,
        "schedule": _fmt_schedule(j.schedule),
        "enabled": j.enabled,
        "last_run_at": j.last_run_at,
        "message": j.message,
    } for j in jobs]


def _daemon_states_payload() -> list:
    """Return live daemon scheduler states as plain dicts (best-effort)."""
    try:
        from praisonai.scheduler.state_manager import SchedulerStateManager
        state_manager = SchedulerStateManager()
        state_manager.cleanup_dead_processes()
        states = state_manager.list_all()
        out = []
        for s in states:
            pid = s.get("pid", 0)
            out.append({
                "source": "daemon",
                "name": s.get("name", "unknown"),
                "pid": pid,
                "status": "running" if state_manager.is_process_alive(pid) else "stopped",
                "interval": s.get("interval", "unknown"),
                "task": s.get("task", ""),
            })
        return out
    except Exception:
        return []


def _print_store_jobs(output, jobs) -> None:
    """Print store-backed ScheduleJobs with a source label (human output)."""
    if not jobs:
        return
    output.print_header(f"Store schedules ({len(jobs)}):")
    for j in jobs:
        status = "enabled" if j.enabled else "paused"
        line = (
            f"  [store] {j.name} (id: {j.id}) [{status}] — "
            f"{_fmt_schedule(j.schedule)} — last run: {_fmt_ts(j.last_run_at)}"
        )
        output.print_info(line)


@app.command("list")
def schedule_list(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List scheduled jobs (store-backed jobs and daemon schedulers)."""
    output = get_output_controller()
    try:
        from praisonaiagents.tools.schedule_tools import _get_store
        jobs = _get_store().list()
    except Exception:
        jobs = []

    if json_output:
        # Emit a single valid JSON document so consumers can parse stdout.
        # The daemon list handler only prints a human table, so its states are
        # gathered directly here instead of delegating (which would corrupt the
        # JSON payload).
        import json as _json
        print(_json.dumps({
            "store": _store_jobs_payload(jobs),
            "daemon": _daemon_states_payload(),
        }))
        raise typer.Exit(0)

    _print_store_jobs(output, jobs)
    _run_schedule(["list"])
    raise typer.Exit(0)


@app.command("runs")
def schedule_runs(
    name: str = typer.Argument(..., help="Schedule name or id"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max run records to show"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show past run history for a store-backed schedule."""
    output = get_output_controller()
    try:
        from praisonaiagents.tools.schedule_tools import _get_store
        store = _get_store()
        job = store.get(name) or store.get_by_name(name)
        if job is None:
            output.print_error(f"Schedule '{name}' not found.")
            raise typer.Exit(1)
        records = store.get_history(job_id=job.id, limit=limit)
        if json_output:
            import json as _json
            print(_json.dumps([r.to_dict() for r in records]))
            raise typer.Exit(0)
        if not records:
            output.print_info(f"No run history for '{job.name}'.")
            raise typer.Exit(0)
        output.print_header(f"Runs for '{job.name}' ({len(records)}):")
        for r in records:
            delivered = "delivered" if r.delivered else "not-delivered"
            detail = f" — {r.error}" if r.error else ""
            output.print_info(
                f"  {_fmt_ts(r.timestamp)} [{r.status}] "
                f"{r.duration:.1f}s {delivered}{detail}"
            )
    except typer.Exit:
        raise
    except ImportError as e:
        output.print_error(f"Schedule tools not available: {e}")
        raise typer.Exit(4)


def _resolve_store_job(ident: str):
    """Return (store, job) for ``ident`` resolved by id first, then name.

    Resolving by id first guarantees an exact record even when several jobs
    share a name, so a subsequent mutation targets that record and never a
    different same-named job.
    """
    from praisonaiagents.tools.schedule_tools import _get_store
    store = _get_store()
    return store, (store.get(ident) or store.get_by_name(ident))


@app.command("pause")
def schedule_pause(
    name: str = typer.Argument(..., help="Schedule name or id"),
):
    """Pause a store-backed schedule (stops it firing, keeps it)."""
    output = get_output_controller()
    try:
        store, job = _resolve_store_job(name)
        if job is None:
            output.print_error(f"Schedule '{name}' not found.")
            raise typer.Exit(1)
        if not job.enabled:
            output.print_info(f"Schedule '{job.name}' is already paused.")
            raise typer.Exit(0)
        job.enabled = False
        store.update(job)
        output.print_success(f"Schedule '{job.name}' paused.")
    except typer.Exit:
        raise
    except ImportError as e:
        output.print_error(f"Schedule tools not available: {e}")
        raise typer.Exit(4)


@app.command("resume")
def schedule_resume(
    name: str = typer.Argument(..., help="Schedule name or id"),
):
    """Resume a paused store-backed schedule."""
    output = get_output_controller()
    try:
        store, job = _resolve_store_job(name)
        if job is None:
            output.print_error(f"Schedule '{name}' not found.")
            raise typer.Exit(1)
        if job.enabled:
            output.print_info(f"Schedule '{job.name}' is already active.")
            raise typer.Exit(0)
        job.enabled = True
        store.update(job)
        output.print_success(f"Schedule '{job.name}' resumed.")
    except typer.Exit:
        raise
    except ImportError as e:
        output.print_error(f"Schedule tools not available: {e}")
        raise typer.Exit(4)


@app.command("update")
def schedule_update(
    name: str = typer.Argument(..., help="Schedule name or id"),
    schedule: str = typer.Option("", "--schedule", "-s", help="New schedule expression"),
    message: str = typer.Option("", "--message", "-m", help="New prompt / reminder text"),
    tz: str = typer.Option("", "--tz", help="IANA timezone applied when re-parsing --schedule"),
):
    """Update a store-backed schedule's cadence and/or message."""
    output = get_output_controller()
    try:
        store, job = _resolve_store_job(name)
        if job is None:
            output.print_error(f"Schedule '{name}' not found.")
            raise typer.Exit(1)
        changed = []
        if schedule:
            from praisonaiagents.scheduler.parser import parse_schedule
            try:
                job.schedule = parse_schedule(schedule, tz=tz or None)
            except ValueError as e:
                output.print_error(f"Error updating schedule: {e}")
                raise typer.Exit(1)
            # A new cadence must be evaluated fresh (see schedule_tools):
            # clearing last_run_at restarts the schedule from now.
            job.last_run_at = None
            changed.append(f"schedule={schedule}")
        if message:
            job.message = message
            changed.append("message")
        if not changed:
            output.print_info(f"Schedule '{job.name}' unchanged (nothing to update).")
            raise typer.Exit(0)
        store.update(job)
        output.print_success(f"Schedule '{job.name}' updated ({', '.join(changed)}).")
    except typer.Exit:
        raise
    except ImportError as e:
        output.print_error(f"Schedule tools not available: {e}")
        raise typer.Exit(4)


@app.command("remove")
def schedule_remove(
    name: str = typer.Argument(..., help="Schedule name or id"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove a store-backed schedule (run history is retained)."""
    output = get_output_controller()
    try:
        store, job = _resolve_store_job(name)
        if job is None:
            output.print_error(f"Schedule '{name}' not found.")
            raise typer.Exit(1)
        if not confirm and not typer.confirm(f"Remove schedule '{job.name}'?"):
            output.print_info("Cancelled")
            raise typer.Exit(0)
        # Remove the exact resolved record by id so a duplicate name cannot
        # cause a different job to be deleted.
        if store.remove(job.id):
            output.print_success(f"Schedule '{job.name}' removed.")
        else:
            output.print_error(f"Schedule '{job.name}' not found.")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except ImportError as e:
        output.print_error(f"Schedule tools not available: {e}")
        raise typer.Exit(4)


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
    """Delete a scheduled job (store-backed job or daemon scheduler)."""
    output = get_output_controller()

    # Prefer the store: a job authored by ``schedule add`` lives there, and the
    # daemon handler cannot see it. Fall back to the daemon for PID-state jobs.
    store_job = None
    try:
        from praisonaiagents.tools.schedule_tools import _get_store
        store = _get_store()
        store_job = store.get(job_id) or store.get_by_name(job_id)
    except Exception:
        store_job = None

    if not confirm:
        label = store_job.name if store_job is not None else job_id
        if not typer.confirm(f"Delete job {label}?"):
            output.print_info("Cancelled")
            raise typer.Exit(0)

    if store_job is not None:
        # Remove the exact resolved record by id so a duplicate name cannot
        # cause a different job to be deleted.
        if store.remove(store_job.id):
            output.print_success(f"Schedule '{store_job.name}' removed.")
        else:
            output.print_error(f"Schedule '{store_job.name}' not found.")
            raise typer.Exit(1)
        raise typer.Exit(0)

    raise typer.Exit(_run_schedule(["delete", job_id]))


@app.command("describe")
def schedule_describe(
    job_id: str = typer.Argument(..., help="Job ID or name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show job details (store-backed job or daemon scheduler)."""
    output = get_output_controller()

    # Prefer the store: a job authored by ``schedule add`` lives there and the
    # daemon handler cannot see it. Fall back to the daemon for PID-state jobs.
    store_job = None
    try:
        from praisonaiagents.tools.schedule_tools import _get_store
        store = _get_store()
        store_job = store.get(job_id) or store.get_by_name(job_id)
    except Exception:
        store_job = None

    if store_job is not None:
        if json_output:
            import json as _json
            payload = _store_jobs_payload([store_job])[0]
            payload["agent_id"] = store_job.agent_id
            payload["principal"] = getattr(store_job, "principal", None)
            payload["delete_after_run"] = getattr(store_job, "delete_after_run", False)
            print(_json.dumps(payload))
            raise typer.Exit(0)
        status = "enabled" if store_job.enabled else "paused"
        output.print_header(f"Schedule '{store_job.name}' [store]")
        output.print_info(f"  id:          {store_job.id}")
        output.print_info(f"  status:      {status}")
        output.print_info(f"  schedule:    {_fmt_schedule(store_job.schedule)}")
        output.print_info(f"  last run:    {_fmt_ts(store_job.last_run_at)}")
        if store_job.agent_id:
            output.print_info(f"  agent:       {store_job.agent_id}")
        if getattr(store_job, "delete_after_run", False):
            output.print_info("  one-shot:    yes (delete_after_run)")
        if store_job.message:
            output.print_info(f"  message:     {store_job.message}")
        raise typer.Exit(0)

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


# ── Blueprint commands ─────────────────────────────────────────────────


@app.command("blueprint")
def schedule_blueprint(
    blueprint_name: str = typer.Argument(..., help="Blueprint name (morning-brief, important-mail, weekly-review)"),
    hour: Optional[int] = typer.Option(None, "--hour", help="Delivery hour (0-23)"),
    minute: Optional[int] = typer.Option(None, "--minute", help="Delivery minute (0-59)"),
    weekdays: Optional[str] = typer.Option(None, "--weekdays", help="Days: mon-fri, daily, weekends, or a single day"),
    focus: Optional[str] = typer.Option(None, "--focus", help="Focus area"),
    interval: Optional[int] = typer.Option(None, "--interval", help="Interval in minutes (for interval-based blueprints)"),
    keywords: Optional[str] = typer.Option(None, "--keywords", help="Priority keywords (for important-mail)"),
    deliver: str = typer.Option("", "--deliver", "-d", help="Delivery target"),
    agent: str = typer.Option("", "--agent", "-a", help="Agent ID"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Create a schedule from a blueprint template.

    Examples:
        praisonai schedule blueprint morning-brief --hour 8 --weekdays mon-fri --deliver telegram
        praisonai schedule blueprint important-mail --interval 30 --keywords urgent,deadline --deliver telegram
        praisonai schedule blueprint weekly-review --hour 17 --weekdays fri --focus tech
    """
    output = get_output_controller()
    try:
        from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue
        from praisonaiagents.tools.schedule_tools import schedule_add as _schedule_add

        catalogue = BlueprintCatalogue()
        bp = catalogue.get_blueprint(blueprint_name)
        if bp is None:
            available = [b.name for b in catalogue.list_blueprints()]
            output.print_error(
                f"Blueprint '{blueprint_name}' not found. "
                f"Available: {', '.join(available)}"
            )
            raise typer.Exit(1)

        # Build slots dict from CLI args
        cli_slot_map: dict = {
            "hour": hour, "minute": minute, "weekdays": weekdays,
            "focus": focus, "interval_minutes": interval, "keywords": keywords,
        }
        slots = {}
        for slot in bp.slots:
            cli_val = cli_slot_map.get(slot.name)
            if cli_val is not None:
                slots[slot.name] = cli_val

        resolved = catalogue.resolve_slots(bp, slots)
        prompt = catalogue.materialize_prompt(bp, resolved)
        schedule_expr = catalogue.materialize_schedule(bp, resolved)
        final_deliver = deliver or bp.default_deliver

        result = _schedule_add(
            name=blueprint_name,
            schedule=schedule_expr,
            message=prompt,
            deliver=final_deliver,
            agent_id=agent or bp.default_agent,
        )

        if json_output:
            import json as _json
            print(_json.dumps({"result": result, "blueprint": blueprint_name,
                               "schedule": schedule_expr}))
        else:
            output.print_success(result)
    except typer.Exit:
        raise
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command("blueprint-list")
def schedule_blueprint_list(
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List available blueprints."""
    output = get_output_controller()
    try:
        from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue

        catalogue = BlueprintCatalogue()
        blueprints = catalogue.list_blueprints(category=category)

        if json_output:
            import json as _json
            print(_json.dumps([{
                "name": bp.name,
                "description": bp.description,
                "category": bp.category,
                "tags": bp.tags,
                "slots": [
                    {"name": s.name, "type": s.type, "label": s.label,
                     "default": s.default, "choices": s.choices}
                    for s in bp.slots
                ],
                "default_deliver": bp.default_deliver,
                "builtin": bp.builtin,
            } for bp in blueprints]))
        else:
            if not blueprints:
                output.print_info("No blueprints found.")
            else:
                output.print_header(f"Available blueprints ({len(blueprints)}):")
                for bp in blueprints:
                    slot_desc = ", ".join(
                        f"{s.name}={s.default}" if s.default is not None else s.name
                        for s in bp.slots
                    )
                    tag = " [builtin]" if bp.builtin else " [custom]"
                    output.print_info(f"  {bp.name} [{bp.category}]{tag} — {bp.description}")
                    output.print_info(f"    Slots: {slot_desc}")
                    if bp.default_deliver:
                        output.print_info(f"    Default delivery: {bp.default_deliver}")
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


# ── Suggestion commands ─────────────────────────────────────────────────


@app.command("suggestions")
def schedule_suggestions(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List pending automation suggestions."""
    output = get_output_controller()
    try:
        from praisonai.scheduler.suggestion_engine import SuggestionEngine

        engine = SuggestionEngine()
        pending = engine.pending()

        if json_output:
            import json as _json
            print(_json.dumps([{
                "id": s.id,
                "blueprint_name": s.blueprint_name,
                "slots": s.slots,
                "reason": s.reason,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
            } for s in pending]))
        else:
            if not pending:
                output.print_info("No pending suggestions.")
            else:
                output.print_header(f"Suggestions ({len(pending)}):")
                for s in pending:
                    slot_str = ", ".join(f"{k}={v}" for k, v in s.slots.items())
                    output.print_info(f"  [{s.id}] Blueprint: {s.blueprint_name}")
                    output.print_info(f"    Reason: {s.reason or 'N/A'}")
                    output.print_info(f"    Slots: {slot_str or '(defaults)'}")
                    output.print_info(f"    Accept: praisonai schedule suggestion-accept {s.id}")
                    output.print_info(f"    Dismiss: praisonai schedule suggestion-dismiss {s.id}")
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command("suggestion-accept")
def schedule_suggestion_accept(
    suggestion_id: str = typer.Argument(..., help="Suggestion ID to accept"),
    deliver: str = typer.Option("", "--deliver", "-d", help="Override delivery target"),
):
    """Accept a suggestion and create the schedule job."""
    output = get_output_controller()
    try:
        from praisonai.scheduler.suggestion_engine import SuggestionEngine
        from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue
        from praisonaiagents.tools.schedule_tools import schedule_add as _schedule_add

        engine = SuggestionEngine()
        sug = engine.get_suggestion(suggestion_id)
        if sug is None or sug.dismissed or sug.accepted:
            output.print_error(f"Suggestion '{suggestion_id}' not found or already handled.")
            raise typer.Exit(1)

        # Reject expired suggestions (expires_at == 0 means no expiry)
        import time as _time
        if sug.expires_at != 0 and sug.expires_at <= _time.time():
            output.print_error(f"Suggestion '{suggestion_id}' has expired.")
            raise typer.Exit(1)

        catalogue = BlueprintCatalogue()
        bp = catalogue.get_blueprint(sug.blueprint_name)
        if bp is None:
            output.print_error(f"Blueprint '{sug.blueprint_name}' for suggestion not found.")
            raise typer.Exit(1)

        resolved = catalogue.resolve_slots(bp, sug.slots)
        prompt = catalogue.materialize_prompt(bp, resolved)
        schedule_expr = catalogue.materialize_schedule(bp, resolved)
        final_deliver = deliver or sug.deliver or bp.default_deliver

        result = _schedule_add(
            name=sug.blueprint_name,
            schedule=schedule_expr,
            message=prompt,
            deliver=final_deliver,
            accept_suggestion=suggestion_id,
        )

        if result.startswith("Error") or "already exists" in result:
            output.print_error(result)
            raise typer.Exit(1)
        output.print_success(f"Suggestion accepted. {result}")
    except typer.Exit:
        raise
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command("suggestion-dismiss")
def schedule_suggestion_dismiss(
    suggestion_id: str = typer.Argument(..., help="Suggestion ID to dismiss"),
):
    """Dismiss a suggestion without creating a job."""
    output = get_output_controller()
    try:
        from praisonai.scheduler.suggestion_engine import SuggestionEngine
        engine = SuggestionEngine()
        ok = engine.dismiss(suggestion_id)
        if ok:
            output.print_info(f"Suggestion '{suggestion_id}' dismissed.")
        else:
            output.print_error(f"Suggestion '{suggestion_id}' not found.")
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.command("suggestion-propose")
def schedule_suggestion_propose(
    blueprint_name: str = typer.Argument(..., help="Blueprint to suggest"),
    reason: str = typer.Option("", "--reason", "-r", help="Why this is being suggested"),
    hour: Optional[int] = typer.Option(None, "--hour"),
    minute: Optional[int] = typer.Option(None, "--minute"),
    weekdays: Optional[str] = typer.Option(None, "--weekdays"),
    focus: Optional[str] = typer.Option(None, "--focus"),
    interval: Optional[int] = typer.Option(None, "--interval"),
    keywords: Optional[str] = typer.Option(None, "--keywords", help="Priority keywords (for important-mail)"),
    deliver: str = typer.Option("", "--deliver", "-d", help="Suggested delivery target"),
):
    """Propose a blueprint as a suggestion (manual/CLI trigger)."""
    output = get_output_controller()
    try:
        from praisonai.scheduler.blueprint_catalogue import BlueprintCatalogue
        from praisonai.scheduler.suggestion_engine import SuggestionEngine

        catalogue = BlueprintCatalogue()
        bp = catalogue.get_blueprint(blueprint_name)
        if bp is None:
            available = [b.name for b in catalogue.list_blueprints()]
            output.print_error(
                f"Blueprint '{blueprint_name}' not found. "
                f"Available: {', '.join(available)}"
            )
            raise typer.Exit(1)

        cli_slot_map: dict = {
            "hour": hour, "minute": minute, "weekdays": weekdays,
            "focus": focus, "interval_minutes": interval,
            "keywords": keywords,
        }
        slots = {}
        for slot in bp.slots:
            val = cli_slot_map.get(slot.name)
            if val is not None:
                slots[slot.name] = val

        engine = SuggestionEngine()
        sug_id = engine.propose(
            blueprint_name=blueprint_name,
            slots=slots,
            deliver=deliver,
            reason=reason or f"Suggestion from CLI for {blueprint_name}",
        )

        if sug_id:
            output.print_success(f"Suggestion created (id: {sug_id}).")
            output.print_info(f"  Accept: praisonai schedule suggestion-accept {sug_id}")
            output.print_info(f"  Dismiss: praisonai schedule suggestion-dismiss {sug_id}")
        else:
            output.print_warning("Suggestion not created (cap reached or duplicate).")
    except typer.Exit:
        raise
    except Exception as e:
        output.print_error(str(e))
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def schedule_callback(ctx: typer.Context):
    """Show schedule help or list jobs."""
    if ctx.invoked_subcommand is None:
        schedule_list(json_output=False)
