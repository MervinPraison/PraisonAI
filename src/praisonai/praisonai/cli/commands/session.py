"""
Session command group for PraisonAI CLI.

Provides session management:
- session list: List all sessions
- session resume: Resume a session
- session delete: Delete a session
- session export: Export a session
"""

from typing import Optional

import typer

from ..output.console import get_output_controller
from ..state.sessions import get_session_manager, set_session_backend

app = typer.Typer(help="Session management")


def _create_backend(backend_type: str, storage_path: Optional[str]):
    """Create storage backend from CLI options."""
    try:
        if backend_type == "file":
            from praisonaiagents.storage import FileBackend
            return FileBackend(storage_dir=storage_path or "~/.praison/sessions")
        elif backend_type == "sqlite":
            from praisonaiagents.storage import SQLiteBackend
            db_path = storage_path or "~/.praison/sessions.db"
            return SQLiteBackend(db_path=db_path)
        elif backend_type.startswith("redis://"):
            from praisonaiagents.storage import RedisBackend
            return RedisBackend(url=backend_type, prefix="session:")
        else:
            return None
    except Exception:
        return None


@app.command("list")
def session_list(
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Maximum number of sessions to show",
    ),
    storage_backend: Optional[str] = typer.Option(
        None,
        "--storage-backend",
        help="Storage backend: 'file', 'sqlite', or 'redis://url'",
    ),
    storage_path: Optional[str] = typer.Option(
        None,
        "--storage-path",
        help="Path for storage backend",
    ),
):
    """List all sessions."""
    output = get_output_controller()
    
    # Configure backend if specified
    if storage_backend:
        backend = _create_backend(storage_backend, storage_path)
        if backend:
            set_session_backend(backend)
    
    manager = get_session_manager()
    
    sessions = manager.list(limit=limit)
    
    if output.is_json_mode:
        output.print_json({
            "sessions": [s.to_dict() for s in sessions]
        })
        return
    
    if not sessions:
        output.print_info("No sessions found")
        return
    
    headers = ["ID", "Name", "Status", "Events", "Updated"]
    rows = []
    for s in sessions:
        rows.append([
            s.session_id[:20] + "..." if len(s.session_id) > 20 else s.session_id,
            s.name or "-",
            s.status,
            str(s.event_count),
            s.updated_at.strftime("%Y-%m-%d %H:%M"),
        ])
    
    output.print_table(headers, rows, title="Sessions")


@app.command("resume")
def session_resume(
    session_id: str = typer.Argument(..., help="Session ID to resume"),
):
    """Resume a session."""
    output = get_output_controller()
    manager = get_session_manager()
    
    session = manager.get(session_id)
    
    if not session:
        output.print_error(
            f"Session not found: {session_id}",
            remediation="Use 'praisonai session list' to see available sessions"
        )
        raise typer.Exit(1)
    
    # Load session events
    events = manager.get_events(session_id)
    
    if output.is_json_mode:
        output.print_json({
            "session": session.to_dict(),
            "events": events,
            "message": "Session loaded. True resume not supported - showing transcript.",
        })
        return
    
    output.print_panel(
        f"Session: {session.name or session.session_id}\n"
        f"Run ID: {session.run_id}\n"
        f"Trace ID: {session.trace_id}\n"
        f"Events: {session.event_count}\n"
        f"Status: {session.status}",
        title="Session Loaded"
    )
    
    output.print_warning(
        "True session resume is not yet supported. "
        "Showing session transcript instead."
    )
    
    # Show recent events
    if events:
        output.print("\n--- Recent Events ---\n")
        for event in events[-10:]:
            event_type = event.get("event", "unknown")
            message = event.get("message", "")
            output.print(f"[{event_type}] {message}")


@app.command("delete")
def session_delete(
    session_id: str = typer.Argument(..., help="Session ID to delete"),
    confirm: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation",
    ),
):
    """Delete a session."""
    output = get_output_controller()
    manager = get_session_manager()
    
    session = manager.get(session_id)
    
    if not session:
        output.print_error(f"Session not found: {session_id}")
        raise typer.Exit(1)
    
    if not confirm:
        confirmed = typer.confirm(f"Delete session {session_id}?")
        if not confirmed:
            output.print_info("Cancelled")
            raise typer.Exit(0)
    
    deleted = manager.delete(session_id)
    
    if output.is_json_mode:
        output.print_json({"deleted": deleted, "session_id": session_id})
    else:
        if deleted:
            output.print_success(f"Deleted session: {session_id}")
        else:
            output.print_error(f"Failed to delete session: {session_id}")
            raise typer.Exit(1)


@app.command("export")
def session_export(
    session_id: str = typer.Argument(..., help="Session ID to export"),
    format: str = typer.Option(
        "md",
        "--format",
        "-f",
        help="Export format: md or json",
    ),
    output_file: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path",
    ),
):
    """Export a session."""
    output = get_output_controller()
    manager = get_session_manager()
    
    content = manager.export(session_id, format=format)
    
    if content is None:
        output.print_error(f"Session not found: {session_id}")
        raise typer.Exit(1)
    
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content)
        output.print_success(f"Exported to: {output_file}")
    else:
        print(content)


@app.command("show")
def session_show(
    session_id: str = typer.Argument(..., help="Session ID to show"),
):
    """Show session details."""
    output = get_output_controller()
    manager = get_session_manager()
    
    session = manager.get(session_id)
    
    if not session:
        output.print_error(f"Session not found: {session_id}")
        raise typer.Exit(1)
    
    if output.is_json_mode:
        output.print_json(session.to_dict())
        return
    
    output.print_panel(
        f"Session ID: {session.session_id}\n"
        f"Name: {session.name or '-'}\n"
        f"Run ID: {session.run_id}\n"
        f"Trace ID: {session.trace_id}\n"
        f"Created: {session.created_at.isoformat()}\n"
        f"Updated: {session.updated_at.isoformat()}\n"
        f"Status: {session.status}\n"
        f"Events: {session.event_count}\n"
        f"Workspace: {session.workspace or '-'}",
        title="Session Details"
    )


@app.command("import")
def session_import(
    input_file: str = typer.Argument(..., help="Session file to import (JSON format)"),
):
    """Import a session from a file."""
    import json
    
    output = get_output_controller()
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        output.print_error(f"File not found: {input_file}")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        output.print_error(f"Invalid JSON: {e}")
        raise typer.Exit(1)
    
    # Use InteractiveCore to import
    try:
        from praisonai.cli.interactive import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.import_session(data)
        
        if output.is_json_mode:
            output.print_json({"imported": True, "session_id": session_id})
        else:
            output.print_success(f"Imported session: {session_id}")
            
    except Exception as e:
        output.print_error(f"Import failed: {e}")
        raise typer.Exit(1)
