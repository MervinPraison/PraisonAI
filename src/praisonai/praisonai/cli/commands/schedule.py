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
            **delivery_kwargs
        )

        # ``pre_run``/``condition`` run an arbitrary host shell command, so they
        # are NOT part of the LLM-callable schedule_add surface. The CLI is a
        # trusted, human-driven surface, so set them on the stored job here.
        if (pre_run or condition) and "Error" not in result:
            try:
                from praisonaiagents.tools.schedule_tools import _get_store
                store = _get_store()
                job = store.get_by_name(name)
                if job is not None:
                    job.pre_run = pre_run or None
                    job.condition = condition or None
                    store.update(job)
            except Exception as e:
                output.print_error(f"Failed to set pre-run gate: {e}")
                raise typer.Exit(1)

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
            "focus": focus, "interval_minutes": interval, "interval": interval,
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
