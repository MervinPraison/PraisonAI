"""
CLI Commands for PraisonAI TUI and Queue.

Provides Typer-based CLI commands for:
- praison tui - Launch interactive TUI
- praison run - Execute single task
- praison queue ls/cancel/retry/clear
- praison session ls/resume
"""

import asyncio
import json
import sys
from typing import Optional

try:
    import typer
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    TYPER_AVAILABLE = True
except ImportError:
    TYPER_AVAILABLE = False
    typer = None

console = Console() if TYPER_AVAILABLE else None


def create_tui_app():
    """Create the TUI CLI app."""
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
        workspace: Optional[str] = typer.Option(
            None, "--workspace", "-w",
            help="Workspace directory"
        ),
        session: Optional[str] = typer.Option(
            None, "--session", "-s",
            help="Resume session ID"
        ),
        model: Optional[str] = typer.Option(
            None, "--model", "-m",
            help="Default model"
        ),
        agent: Optional[str] = typer.Option(
            None, "--agent", "-a",
            help="Agent config file (YAML)"
        ),
        no_acp: bool = typer.Option(
            False, "--no-acp",
            help="Disable ACP tools (file operations with plan/approve/apply)"
        ),
        no_lsp: bool = typer.Option(
            False, "--no-lsp",
            help="Disable LSP tools (code intelligence: symbols, definitions)"
        ),
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
            console.print(
                "[red]Textual is required for TUI. Install with:[/red]\n"
                "  pip install praisonai[tui]"
            )
            raise typer.Exit(1)
        
        # Load agent config if provided
        agent_config = {}
        if agent:
            import yaml
            with open(agent, "r") as f:
                agent_config = yaml.safe_load(f)
        
        run_tui(
            workspace=workspace,
            session_id=session,
            model=model,
            agent_config=agent_config,
            enable_acp=not no_acp,
            enable_lsp=not no_lsp,
        )
    
    return app


def create_queue_app():
    """Create the queue CLI app."""
    if not TYPER_AVAILABLE:
        return None
    
    app = typer.Typer(
        name="queue",
        help="Queue management commands",
        no_args_is_help=True,
    )
    
    @app.command("ls")
    def queue_ls(
        state: Optional[str] = typer.Option(
            None, "--state", "-s",
            help="Filter by state (queued, running, succeeded, failed, cancelled)"
        ),
        session: Optional[str] = typer.Option(
            None, "--session",
            help="Filter by session ID"
        ),
        limit: int = typer.Option(
            20, "--limit", "-n",
            help="Maximum number of results"
        ),
        json_output: bool = typer.Option(
            False, "--json", "-j",
            help="Output as JSON"
        ),
    ):
        """List queued runs."""
        from ..queue import QueuePersistence, RunState
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        # Parse state filter
        state_filter = None
        if state:
            try:
                state_filter = RunState(state.lower())
            except ValueError:
                console.print(f"[red]Invalid state: {state}[/red]")
                raise typer.Exit(1)
        
        runs = persistence.list_runs(
            state=state_filter,
            session_id=session,
            limit=limit,
        )
        
        if json_output:
            output = [r.to_dict() for r in runs]
            console.print(json.dumps(output, indent=2, default=str))
            return
        
        if not runs:
            console.print("[dim]No runs found.[/dim]")
            return
        
        # Create table
        table = Table(title="Queue Runs")
        table.add_column("ID", style="cyan")
        table.add_column("Agent", style="green")
        table.add_column("Input", max_width=30)
        table.add_column("State", style="yellow")
        table.add_column("Priority")
        table.add_column("Wait", style="dim")
        table.add_column("Duration", style="dim")
        
        for run in runs:
            state_style = {
                "queued": "yellow",
                "running": "green",
                "succeeded": "cyan",
                "failed": "red",
                "cancelled": "dim",
            }.get(run.state.value, "")
            
            input_preview = run.input_content[:27] + "..." if len(run.input_content) > 30 else run.input_content
            
            table.add_row(
                run.run_id[:8],
                run.agent_name,
                input_preview,
                f"[{state_style}]{run.state.value}[/{state_style}]",
                run.priority.name.lower(),
                f"{run.wait_seconds:.1f}s" if run.wait_seconds else "-",
                f"{run.duration_seconds:.1f}s" if run.duration_seconds else "-",
            )
        
        console.print(table)
        persistence.close()
    
    @app.command("cancel")
    def queue_cancel(
        run_id: str = typer.Argument(..., help="Run ID to cancel"),
    ):
        """Cancel a queued or running run."""
        from ..queue import QueuePersistence, RunState
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        # Find the run
        run = persistence.load_run(run_id)
        if not run:
            # Try partial match
            runs = persistence.list_runs(limit=100)
            matches = [r for r in runs if r.run_id.startswith(run_id)]
            if len(matches) == 1:
                run = matches[0]
            elif len(matches) > 1:
                console.print(f"[yellow]Multiple matches for '{run_id}':[/yellow]")
                for r in matches:
                    console.print(f"  {r.run_id}")
                raise typer.Exit(1)
            else:
                console.print(f"[red]Run not found: {run_id}[/red]")
                raise typer.Exit(1)
        
        if run.state.is_terminal():
            console.print(f"[yellow]Run {run.run_id[:8]} is already {run.state.value}[/yellow]")
            raise typer.Exit(1)
        
        # Update state
        persistence.update_run_state(run.run_id, RunState.CANCELLED)
        console.print(f"[green]Cancelled run: {run.run_id[:8]}[/green]")
        persistence.close()
    
    @app.command("retry")
    def queue_retry(
        run_id: str = typer.Argument(..., help="Run ID to retry"),
    ):
        """Retry a failed run."""
        from ..queue import QueuePersistence, QueuedRun, RunState
        import uuid
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        # Find the run
        run = persistence.load_run(run_id)
        if not run:
            runs = persistence.list_runs(limit=100)
            matches = [r for r in runs if r.run_id.startswith(run_id)]
            if len(matches) == 1:
                run = matches[0]
            else:
                console.print(f"[red]Run not found: {run_id}[/red]")
                raise typer.Exit(1)
        
        if run.state != RunState.FAILED:
            console.print(f"[yellow]Can only retry failed runs (current: {run.state.value})[/yellow]")
            raise typer.Exit(1)
        
        if run.retry_count >= run.max_retries:
            console.print(f"[yellow]Max retries reached ({run.retry_count}/{run.max_retries})[/yellow]")
            raise typer.Exit(1)
        
        # Create new run
        new_run = QueuedRun(
            run_id=str(uuid.uuid4())[:8],
            agent_name=run.agent_name,
            input_content=run.input_content,
            state=RunState.QUEUED,
            priority=run.priority,
            session_id=run.session_id,
            workspace=run.workspace,
            retry_count=run.retry_count + 1,
            max_retries=run.max_retries,
            parent_run_id=run.run_id,
            config=run.config,
        )
        
        persistence.save_run(new_run)
        console.print(f"[green]Created retry run: {new_run.run_id} (from {run.run_id[:8]})[/green]")
        persistence.close()
    
    @app.command("clear")
    def queue_clear(
        force: bool = typer.Option(
            False, "--force", "-f",
            help="Skip confirmation"
        ),
    ):
        """Clear all queued runs."""
        from ..queue import QueuePersistence, RunState
        
        if not force:
            confirm = typer.confirm("Clear all queued runs?")
            if not confirm:
                raise typer.Abort()
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        # Get queued runs
        runs = persistence.list_runs(state=RunState.QUEUED, limit=1000)
        
        count = 0
        for run in runs:
            persistence.update_run_state(run.run_id, RunState.CANCELLED)
            count += 1
        
        console.print(f"[green]Cleared {count} queued runs[/green]")
        persistence.close()
    
    @app.command("stats")
    def queue_stats(
        session: Optional[str] = typer.Option(
            None, "--session",
            help="Filter by session ID"
        ),
    ):
        """Show queue statistics."""
        from ..queue import QueuePersistence
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        stats = persistence.get_stats(session)
        
        console.print(Panel(
            f"""
[bold]Queue Statistics[/bold]

Queued:     {stats.queued_count}
Running:    {stats.running_count}
Succeeded:  {stats.succeeded_count}
Failed:     {stats.failed_count}
Cancelled:  {stats.cancelled_count}

Total Runs: {stats.total_runs}
Avg Wait:   {stats.avg_wait_seconds:.1f}s
Avg Duration: {stats.avg_duration_seconds:.1f}s
""",
            title="Queue Stats"
        ))
        persistence.close()
    
    return app


def create_session_app():
    """Create the session CLI app."""
    if not TYPER_AVAILABLE:
        return None
    
    app = typer.Typer(
        name="session",
        help="Session management commands",
        no_args_is_help=True,
    )
    
    @app.command("ls")
    def session_ls(
        limit: int = typer.Option(
            20, "--limit", "-n",
            help="Maximum number of results"
        ),
    ):
        """List recent sessions."""
        from ..queue import QueuePersistence
        from datetime import datetime
        
        persistence = QueuePersistence()
        persistence.initialize()
        
        sessions = persistence.list_sessions(limit=limit)
        
        if not sessions:
            console.print("[dim]No sessions found.[/dim]")
            return
        
        table = Table(title="Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("User")
        table.add_column("Created", style="dim")
        table.add_column("Updated", style="dim")
        
        for session in sessions:
            created = datetime.fromtimestamp(session["created_at"]).strftime("%Y-%m-%d %H:%M")
            updated = datetime.fromtimestamp(session["updated_at"]).strftime("%Y-%m-%d %H:%M")
            
            table.add_row(
                session["session_id"][:8],
                session.get("user_id", "-"),
                created,
                updated,
            )
        
        console.print(table)
        persistence.close()
    
    @app.command("resume")
    def session_resume(
        session_id: str = typer.Argument(..., help="Session ID to resume"),
    ):
        """Resume a session in TUI."""
        try:
            from .app import run_tui
        except ImportError:
            console.print(
                "[red]Textual is required for TUI. Install with:[/red]\n"
                "  pip install praisonai[tui]"
            )
            raise typer.Exit(1)
        
        run_tui(session_id=session_id)
    
    return app


def create_run_command():
    """Create the run command."""
    if not TYPER_AVAILABLE:
        return None
    
    def run_command(
        prompt: str = typer.Argument(..., help="Prompt to execute"),
        agent: Optional[str] = typer.Option(
            None, "--agent", "-a",
            help="Agent config file (YAML)"
        ),
        model: Optional[str] = typer.Option(
            None, "--model", "-m",
            help="Model to use"
        ),
        stream: bool = typer.Option(
            True, "--stream/--no-stream",
            help="Stream output"
        ),
        priority: str = typer.Option(
            "normal", "--priority", "-p",
            help="Run priority (low, normal, high, urgent)"
        ),
    ):
        """Run a single agent task."""
        from ..queue import QueueManager, QueueConfig, RunPriority
        
        # Parse priority
        try:
            run_priority = RunPriority.from_string(priority)
        except (ValueError, KeyError):
            console.print(f"[red]Invalid priority: {priority}[/red]")
            raise typer.Exit(1)
        
        # Load agent config
        agent_config = {}
        if agent:
            import yaml
            with open(agent, "r") as f:
                agent_config = yaml.safe_load(f)
        
        # Set model
        if model:
            agent_config["model"] = model
        
        async def execute():
            output_chunks = []
            
            async def on_output(run_id: str, chunk: str):
                output_chunks.append(chunk)
                if stream:
                    console.print(chunk, end="")
            
            async def on_complete(run_id: str, run):
                if not stream:
                    console.print(run.output_content or "".join(output_chunks))
            
            async def on_error(run_id: str, error: Exception):
                console.print(f"\n[red]Error: {error}[/red]")
            
            config = QueueConfig(enable_persistence=False)
            manager = QueueManager(
                config=config,
                on_output=on_output,
                on_complete=on_complete,
                on_error=on_error,
            )
            
            await manager.start(recover=False)
            
            try:
                run_id = await manager.submit(
                    input_content=prompt,
                    agent_name=agent_config.get("name", "Assistant"),
                    priority=run_priority,
                    config={"agent_config": agent_config},
                )
                
                # Wait for completion
                while True:
                    run = manager.get_run(run_id)
                    if run and run.state.is_terminal():
                        break
                    await asyncio.sleep(0.1)
                
                if stream:
                    console.print()  # Newline after streaming
                    
            finally:
                await manager.stop()
        
        asyncio.run(execute())
    
    return run_command


# Main CLI integration
def register_tui_commands(app):
    """Register TUI commands with the main CLI app."""
    if not TYPER_AVAILABLE:
        return
    
    tui_app = create_tui_app()
    queue_app = create_queue_app()
    session_app = create_session_app()
    run_cmd = create_run_command()
    
    if tui_app:
        app.add_typer(tui_app, name="tui")
    if queue_app:
        app.add_typer(queue_app, name="queue")
    if session_app:
        app.add_typer(session_app, name="session")
    if run_cmd:
        app.command("run")(run_cmd)


# Standalone entry point
def main():
    """Main entry point for TUI CLI."""
    if not TYPER_AVAILABLE:
        print("Typer is required. Install with: pip install typer")
        sys.exit(1)
    
    app = typer.Typer(
        name="praison-tui",
        help="PraisonAI TUI and Queue CLI",
    )
    
    register_tui_commands(app)
    
    # Add direct tui command
    @app.callback(invoke_without_command=True)
    def default(
        ctx: typer.Context,
        workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
        session: Optional[str] = typer.Option(None, "--session", "-s"),
        model: Optional[str] = typer.Option(None, "--model", "-m"),
    ):
        """Launch TUI if no subcommand given."""
        if ctx.invoked_subcommand is None:
            try:
                from .app import run_tui
                run_tui(workspace=workspace, session_id=session, model=model)
            except ImportError:
                console.print(
                    "[red]Textual is required for TUI. Install with:[/red]\n"
                    "  pip install praisonai[tui]"
                )
                raise typer.Exit(1)
    
    app()


if __name__ == "__main__":
    main()
