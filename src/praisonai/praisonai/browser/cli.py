"""Browser CLI commands for PraisonAI.

Commands:
    praisonai browser start   - Start the browser automation server
    praisonai browser stop    - Stop the server
    praisonai browser sessions - List active sessions
"""

import typer
from typing import Optional
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="browser",
    help="Browser automation commands",
    no_args_is_help=True,
)

console = Console()


@app.command("start")
def start_server(
    port: int = typer.Option(8765, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("0.0.0.0", "--host", "-H", help="Host to bind to"),
    model: str = typer.Option("gpt-4o-mini", "--model", "-m", help="LLM model to use"),
    max_steps: int = typer.Option(20, "--max-steps", help="Maximum steps per session"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
):
    """Start the browser automation server.
    
    The server provides a WebSocket interface for the Chrome Extension
    to communicate with PraisonAI agents.
    
    Example:
        praisonai browser start --port 8765 --model gpt-4o
    """
    try:
        from praisonai.browser import BrowserServer
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("Install required dependencies: pip install fastapi uvicorn")
        raise typer.Exit(1)
    
    server = BrowserServer(
        host=host,
        port=port,
        model=model,
        max_steps=max_steps,
        verbose=verbose,
    )
    
    try:
        server.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command("sessions")
def list_sessions(
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum sessions to show"),
):
    """List browser automation sessions.
    
    Example:
        praisonai browser sessions --status running
        praisonai browser sessions --limit 10
    """
    try:
        from praisonai.browser.sessions import SessionManager
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    manager = SessionManager()
    sessions = manager.list_sessions(status=status, limit=limit)
    
    if not sessions:
        console.print("[dim]No sessions found[/dim]")
        return
    
    # Create table
    table = Table(title="Browser Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Goal", max_width=40)
    table.add_column("Status", style="bold")
    table.add_column("Started")
    table.add_column("URL", max_width=30)
    
    import datetime
    
    for session in sessions:
        started = datetime.datetime.fromtimestamp(session["started_at"]).strftime("%H:%M:%S")
        status_style = {
            "running": "green",
            "completed": "blue",
            "failed": "red",
            "stopped": "yellow",
        }.get(session["status"], "white")
        
        table.add_row(
            session["session_id"][:8],
            session["goal"][:40] + ("..." if len(session["goal"]) > 40 else ""),
            f"[{status_style}]{session['status']}[/{status_style}]",
            started,
            session.get("current_url", "")[:30] or "-",
        )
    
    console.print(table)
    manager.close()


@app.command("history")
def show_history(
    session_id: str = typer.Argument(..., help="Session ID to show history for"),
):
    """Show step-by-step history for a session.
    
    Example:
        praisonai browser history abc12345
    """
    try:
        from praisonai.browser.sessions import SessionManager
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    manager = SessionManager()
    
    # Find session (support partial ID)
    sessions = manager.list_sessions(limit=100)
    matched = [s for s in sessions if s["session_id"].startswith(session_id)]
    
    if not matched:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)
    
    if len(matched) > 1:
        console.print(f"[yellow]Multiple matches:[/yellow] Please be more specific")
        for s in matched:
            console.print(f"  {s['session_id']}")
        raise typer.Exit(1)
    
    full_id = matched[0]["session_id"]
    session = manager.get_session(full_id)
    
    if not session:
        console.print(f"[red]Session not found:[/red] {session_id}")
        raise typer.Exit(1)
    
    # Print session info
    console.print(f"\n[bold]Session:[/bold] {session['session_id']}")
    console.print(f"[bold]Goal:[/bold] {session['goal']}")
    console.print(f"[bold]Status:[/bold] {session['status']}")
    console.print(f"[bold]Steps:[/bold] {len(session['steps'])}")
    
    # Print steps
    console.print("\n[bold]History:[/bold]")
    
    for step in session["steps"]:
        console.print(f"\n[cyan]Step {step['step_number']}[/cyan]")
        if step.get("action"):
            action = step["action"]
            console.print(f"  [dim]Action:[/dim] {action.get('action', 'unknown')}")
            if action.get("selector"):
                console.print(f"  [dim]Selector:[/dim] {action['selector']}")
            if action.get("text"):
                console.print(f"  [dim]Text:[/dim] {action['text']}")
            if action.get("thought"):
                console.print(f"  [dim]Thought:[/dim] {action['thought'][:100]}...")
    
    manager.close()


@app.command("clear")
def clear_sessions(
    all_sessions: bool = typer.Option(False, "--all", "-a", help="Clear all sessions"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Clear sessions with status"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Clear session history.
    
    Example:
        praisonai browser clear --status completed --yes
        praisonai browser clear --all --yes
    """
    try:
        from praisonai.browser.sessions import SessionManager
    except ImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    if not all_sessions and not status:
        console.print("[yellow]Please specify --all or --status[/yellow]")
        raise typer.Exit(1)
    
    manager = SessionManager()
    sessions = manager.list_sessions(status=status, limit=1000)
    
    if not sessions:
        console.print("[dim]No sessions to clear[/dim]")
        return
    
    if not confirm:
        if not typer.confirm(f"Delete {len(sessions)} sessions?"):
            raise typer.Abort()
    
    deleted = 0
    for session in sessions:
        if manager.delete_session(session["session_id"]):
            deleted += 1
    
    console.print(f"[green]Deleted {deleted} sessions[/green]")
    manager.close()


if __name__ == "__main__":
    app()
