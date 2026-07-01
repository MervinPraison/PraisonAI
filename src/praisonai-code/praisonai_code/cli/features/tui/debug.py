"""
Debug and Simulation CLI Commands for PraisonAI TUI.

Provides headless TUI simulation, tracing, and debugging capabilities.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.live import Live
    from rich.text import Text
    TYPER_AVAILABLE = True
except ImportError:
    TYPER_AVAILABLE = False
    typer = None

console = Console() if TYPER_AVAILABLE else None


def create_debug_app():
    """Create the debug CLI app with simulation commands."""
    if not TYPER_AVAILABLE:
        return None
    
    app = typer.Typer(
        name="tui",
        help="Terminal UI (Textual-based full TUI)",
        no_args_is_help=False,  # Allow running without subcommand
    )
    
    @app.callback(invoke_without_command=True)
    def tui_main(
        ctx: typer.Context,
        workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
        session: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
        model: Optional[str] = typer.Option(None, "--model", "-m", help="Default model"),
        debug: bool = typer.Option(False, "--debug", "-d", help="Enable debug overlays"),
        log_jsonl: Optional[str] = typer.Option(None, "--log-jsonl", help="Write events to JSONL file"),
        profile: bool = typer.Option(False, "--profile", help="Enable performance profiling"),
    ):
        """
        Launch the interactive TUI (Textual-based).
        
        This is a full terminal UI with rich widgets. For simpler terminal
        chat, use: praisonai chat
        
        Examples:
            praisonai tui
            praisonai tui --workspace ./project
            praisonai tui --session abc123
        """
        # If a subcommand was invoked, don't run the default
        if ctx.invoked_subcommand is not None:
            return
            
        try:
            from .app import run_tui
        except ImportError:
            console.print("[red]Textual is required for TUI. Install with:[/red]\n  pip install praisonai[tui]")
            raise typer.Exit(1)
        
        # Set debug environment
        if debug:
            import os
            os.environ["PRAISONAI_TUI_DEBUG"] = "1"
        
        if log_jsonl:
            import os
            os.environ["PRAISONAI_TUI_JSONL"] = log_jsonl
        
        run_tui(workspace=workspace, session_id=session, model=model)
    
    @app.command("simulate")
    def tui_simulate(
        script: str = typer.Argument(..., help="Path to simulation script (YAML/JSON)"),
        mock: bool = typer.Option(True, "--mock/--real-llm", help="Use mock provider"),
        pretty: bool = typer.Option(True, "--pretty/--jsonl", help="Output format"),
        assert_mode: bool = typer.Option(False, "--assert", help="Validate expected outcomes"),
        timeout: float = typer.Option(60.0, "--timeout", help="Max execution time"),
    ):
        """Run a headless TUI simulation script."""
        import os
        
        # Safety gate for real LLM
        if not mock:
            if not os.environ.get("PRAISONAI_REAL_LLM"):
                console.print("[red]Real LLM mode requires PRAISONAI_REAL_LLM=1 environment variable[/red]")
                raise typer.Exit(1)
        
        # Load script
        script_path = Path(script)
        if not script_path.exists():
            console.print(f"[red]Script not found: {script}[/red]")
            raise typer.Exit(1)
        
        with open(script_path) as f:
            if script_path.suffix in (".yaml", ".yml"):
                import yaml
                script_data = yaml.safe_load(f)
            else:
                script_data = json.load(f)
        
        # Run simulation
        from .orchestrator import TuiOrchestrator, SimulationRunner, OutputMode
        from ..queue import QueueConfig
        
        output_mode = OutputMode.PRETTY if pretty else OutputMode.JSONL
        
        config = QueueConfig(enable_persistence=not mock)
        orchestrator = TuiOrchestrator(
            queue_config=config,
            output_mode=output_mode,
            debug=True,
        )
        
        runner = SimulationRunner(orchestrator, assert_mode=assert_mode)
        
        async def run():
            return await asyncio.wait_for(
                runner.run_script(script_data),
                timeout=timeout
            )
        
        try:
            success = asyncio.run(run())
        except asyncio.TimeoutError:
            console.print(f"[red]Simulation timed out after {timeout}s[/red]")
            raise typer.Exit(1)
        
        # Print summary
        summary = runner.get_summary()
        if assert_mode:
            console.print(Panel(
                f"Passed: {summary['assertions_passed']}\n"
                f"Failed: {summary['assertions_failed']}\n"
                f"Errors: {len(summary['errors'])}",
                title="Simulation Results"
            ))
            
            if summary['errors']:
                for error in summary['errors']:
                    console.print(f"[red]  ✗ {error}[/red]")
        
        if not success:
            raise typer.Exit(1)
    
    @app.command("snapshot")
    def tui_snapshot(
        session: Optional[str] = typer.Option(None, "--session", "-s"),
        run_id: Optional[str] = typer.Option(None, "--run", "-r"),
        json_output: bool = typer.Option(False, "--json", "-j"),
    ):
        """Print a TUI-like snapshot of current state."""
        from ..queue import QueuePersistence, RunState
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        # Build snapshot
        snapshot = {
            "timestamp": time.time(),
            "session_id": session,
        }
        
        # Get runs
        runs = persistence.list_runs(session_id=session, limit=100)
        
        queued = [r for r in runs if r.state == RunState.QUEUED]
        running = [r for r in runs if r.state == RunState.RUNNING]
        recent = [r for r in runs if r.state.is_terminal()][-5:]
        
        snapshot["queued_count"] = len(queued)
        snapshot["running_count"] = len(running)
        snapshot["recent_runs"] = [
            {
                "run_id": r.run_id[:8],
                "agent": r.agent_name,
                "state": r.state.value,
                "input": r.input_content[:50],
            }
            for r in recent
        ]
        
        # Get specific run if requested
        if run_id:
            run = persistence.load_run(run_id)
            if run:
                snapshot["run"] = run.to_dict()
        
        # Get session info
        if session:
            session_data = persistence.load_session(session)
            if session_data:
                snapshot["session"] = session_data
        
        persistence.close()
        
        if json_output:
            console.print(json.dumps(snapshot, indent=2, default=str))
        else:
            # Pretty print
            console.print("─" * 60)
            console.print(f"◉ PraisonAI Snapshot │ {time.strftime('%Y-%m-%d %H:%M:%S')}")
            console.print("─" * 60)
            
            console.print(f"\n[bold]Queue Status[/bold]")
            console.print(f"  Queued: {snapshot['queued_count']} │ Running: {snapshot['running_count']}")
            
            if snapshot["recent_runs"]:
                console.print(f"\n[bold]Recent Runs[/bold]")
                for r in snapshot["recent_runs"]:
                    state_color = {
                        "succeeded": "green",
                        "failed": "red",
                        "cancelled": "dim",
                    }.get(r["state"], "yellow")
                    console.print(f"  [{state_color}]{r['run_id']}[/{state_color}] {r['agent']}: {r['input'][:30]}...")
            
            if "run" in snapshot:
                console.print(f"\n[bold]Run Details[/bold]")
                run = snapshot["run"]
                console.print(f"  ID: {run.get('run_id', 'N/A')}")
                console.print(f"  State: {run.get('state', 'N/A')}")
                console.print(f"  Agent: {run.get('agent_name', 'N/A')}")
            
            console.print("─" * 60)
    
    @app.command("trace")
    def tui_trace(
        id: str = typer.Argument(..., help="Session or run ID to trace"),
        follow: bool = typer.Option(False, "--follow", "-f", help="Follow new events"),
        limit: int = typer.Option(50, "--limit", "-n", help="Max events to show"),
    ):
        """Replay events from persistence like a timeline."""
        from ..queue import QueuePersistence
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        # Try to find as session or run
        session = persistence.load_session(id)
        run = persistence.load_run(id)
        
        if not session and not run:
            # Try partial match
            runs = persistence.list_runs(limit=100)
            matches = [r for r in runs if r.run_id.startswith(id) or r.session_id.startswith(id)]
            if matches:
                run = matches[0]
        
        if not session and not run:
            console.print(f"[red]No session or run found for: {id}[/red]")
            persistence.close()
            raise typer.Exit(1)
        
        # Get runs for timeline
        if session:
            runs = persistence.list_runs(session_id=id, limit=limit)
        else:
            runs = [run] if run else []
        
        # Build timeline
        events = []
        for r in runs:
            events.append({
                "timestamp": r.created_at,
                "type": "run_created",
                "run_id": r.run_id[:8],
                "agent": r.agent_name,
                "input": r.input_content[:50],
            })
            if r.started_at:
                events.append({
                    "timestamp": r.started_at,
                    "type": "run_started",
                    "run_id": r.run_id[:8],
                })
            if r.ended_at:
                events.append({
                    "timestamp": r.ended_at,
                    "type": f"run_{r.state.value}",
                    "run_id": r.run_id[:8],
                })
        
        # Sort by timestamp
        events.sort(key=lambda e: e["timestamp"])
        
        persistence.close()
        
        # Print timeline
        console.print(f"\n[bold]Event Timeline for {id[:8]}[/bold]\n")
        
        for event in events[-limit:]:
            ts = time.strftime("%H:%M:%S", time.localtime(event["timestamp"]))
            event_type = event["type"]
            
            type_colors = {
                "run_created": "cyan",
                "run_started": "yellow",
                "run_succeeded": "green",
                "run_failed": "red",
                "run_cancelled": "dim",
            }
            color = type_colors.get(event_type, "white")
            
            line = f"[dim]{ts}[/dim] [{color}]{event_type:15}[/{color}]"
            if "run_id" in event:
                line += f" run={event['run_id']}"
            if "agent" in event:
                line += f" agent={event['agent']}"
            if "input" in event:
                line += f" \"{event['input']}...\""
            
            console.print(line)
        
        if follow:
            console.print("\n[dim]Following... (Ctrl+C to stop)[/dim]")
            # In a real implementation, this would poll for new events
    
    return app


def create_queue_watch_command():
    """Create the queue watch command."""
    if not TYPER_AVAILABLE:
        return None
    
    def queue_watch(
        state: Optional[str] = typer.Option(None, "--state", "-s"),
        agent: Optional[str] = typer.Option(None, "--agent", "-a"),
        run_id: Optional[str] = typer.Option(None, "--run", "-r"),
        jsonl: bool = typer.Option(False, "--jsonl", "-j"),
        interval: float = typer.Option(1.0, "--interval", "-i"),
    ):
        """Watch queue events in real time."""
        from ..queue import QueuePersistence, RunState
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        last_seen = {}
        
        try:
            while True:
                runs = persistence.list_runs(limit=100)
                
                # Filter
                if state:
                    try:
                        state_filter = RunState(state.lower())
                        runs = [r for r in runs if r.state == state_filter]
                    except ValueError:
                        pass
                
                if agent:
                    runs = [r for r in runs if agent.lower() in r.agent_name.lower()]
                
                if run_id:
                    runs = [r for r in runs if r.run_id.startswith(run_id)]
                
                # Check for changes
                for run in runs:
                    key = run.run_id
                    current_state = run.state.value
                    
                    if key not in last_seen or last_seen[key] != current_state:
                        last_seen[key] = current_state
                        
                        if jsonl:
                            event = {
                                "timestamp": time.time(),
                                "run_id": run.run_id,
                                "agent": run.agent_name,
                                "state": current_state,
                            }
                            print(json.dumps(event))
                        else:
                            ts = time.strftime("%H:%M:%S")
                            state_colors = {
                                "queued": "yellow",
                                "running": "cyan",
                                "succeeded": "green",
                                "failed": "red",
                                "cancelled": "dim",
                            }
                            color = state_colors.get(current_state, "white")
                            console.print(
                                f"[dim]{ts}[/dim] [{color}]{current_state:10}[/{color}] "
                                f"{run.run_id[:8]} {run.agent_name}"
                            )
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped watching[/dim]")
        finally:
            persistence.close()
    
    return queue_watch


def create_doctor_command():
    """Create the doctor command for TUI diagnostics."""
    if not TYPER_AVAILABLE:
        return None
    
    def doctor_tui():
        """Validate TUI dependencies, DB schema, and wiring."""
        checks = []
        
        # Check Textual
        try:
            import textual
            checks.append(("Textual", "✓", f"v{textual.__version__}", "green"))
        except ImportError:
            checks.append(("Textual", "✗", "Not installed", "red"))
        
        # Check Rich
        try:
            import rich
            checks.append(("Rich", "✓", f"v{rich.__version__}", "green"))
        except ImportError:
            checks.append(("Rich", "✗", "Not installed", "red"))
        
        # Check Typer
        try:
            import typer
            checks.append(("Typer", "✓", f"v{typer.__version__}", "green"))
        except ImportError:
            checks.append(("Typer", "✗", "Not installed", "red"))
        
        # Check queue modules
        try:
            from ..queue import QueueManager, QueueScheduler, QueuePersistence
            checks.append(("Queue System", "✓", "All modules loaded", "green"))
        except ImportError as e:
            checks.append(("Queue System", "✗", str(e), "red"))
        
        # Check TUI modules
        try:
            from .orchestrator import TuiOrchestrator
            checks.append(("TUI Orchestrator", "✓", "Loaded", "green"))
        except ImportError as e:
            checks.append(("TUI Orchestrator", "✗", str(e), "red"))
        
        # Check events
        try:
            from .events import TUIEvent, TUIEventType
            event_count = len(TUIEventType)
            checks.append(("TUI Events", "✓", f"{event_count} event types", "green"))
        except ImportError as e:
            checks.append(("TUI Events", "✗", str(e), "red"))
        
        # Check DB
        try:
            from ..queue import QueuePersistence
            p = QueuePersistence()
            p.initialize()
            stats = p.get_stats()
            p.close()
            checks.append(("Database", "✓", f"{stats.total_runs} runs in DB", "green"))
        except Exception as e:
            checks.append(("Database", "✗", str(e), "red"))
        
        # Check slash commands
        try:
            from ..slash_commands import SlashCommandRegistry
            registry = SlashCommandRegistry()
            cmd_count = len(registry.commands)
            checks.append(("Slash Commands", "✓", f"{cmd_count} commands", "green"))
        except Exception as e:
            checks.append(("Slash Commands", "⚠", str(e), "yellow"))
        
        # Print results
        console.print("\n[bold]PraisonAI TUI Diagnostics[/bold]\n")
        
        table = Table(show_header=True)
        table.add_column("Component")
        table.add_column("Status")
        table.add_column("Details")
        
        all_ok = True
        for name, status, details, color in checks:
            table.add_row(name, f"[{color}]{status}[/{color}]", details)
            if status == "✗":
                all_ok = False
        
        console.print(table)
        
        if all_ok:
            console.print("\n[green]All checks passed![/green]")
        else:
            console.print("\n[red]Some checks failed. Run 'pip install praisonai[tui]' to install missing dependencies.[/red]")
            raise typer.Exit(1)
    
    return doctor_tui


def register_debug_commands(app):
    """Register debug commands with the main CLI app."""
    if not TYPER_AVAILABLE:
        return
    
    debug_app = create_debug_app()
    watch_cmd = create_queue_watch_command()
    doctor_cmd = create_doctor_command()
    
    if debug_app:
        app.add_typer(debug_app, name="tui")
    
    if watch_cmd:
        # Add to queue subcommand
        pass  # Will be added via queue app
    
    if doctor_cmd:
        # Add doctor --tui option
        pass  # Will be added via main app
