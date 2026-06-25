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
    all_projects: bool = typer.Option(
        False,
        "--all",
        help="Show sessions from all projects (default: current project only)",
    ),
    project_id: Optional[str] = typer.Option(
        None,
        "--project",
        help="Show sessions for specific project ID",
    ),
):
    """List all sessions."""
    output = get_output_controller()
    
    # Handle project-scoped session listing
    if not all_projects and not storage_backend:
        # Use project-scoped session store by default
        from ..state.project_sessions import get_project_session_store
        from ..utils.project import get_project_id, get_project_name
        
        # List sessions for specific or current project
        project_store = get_project_session_store(project_id=project_id)
            
        sessions_data = project_store.list_sessions(limit=limit)
        
        # Convert to expected format
        class SessionInfo:
            def __init__(self, data):
                from datetime import datetime
                
                self.session_id = data.get("session_id", data.get("id", ""))
                self.name = data.get("agent_name", "")
                self.status = data.get("status")  # Use actual status from data if available
                self.event_count = data.get("message_count", 0)
                
                # Parse updated_at string
                updated_str = data.get("updated_at", "")
                try:
                    self.updated_at = datetime.fromisoformat(updated_str.replace('Z', '+00:00')) if updated_str else datetime.now()
                except ValueError:
                    self.updated_at = datetime.now()
                
            def to_dict(self):
                return {
                    "session_id": self.session_id,
                    "name": self.name,
                    "status": self.status,
                    "event_count": self.event_count,
                    "updated_at": self.updated_at.isoformat(),
                }
        
        sessions = [SessionInfo(data) for data in sessions_data]
        
        # Add project info to output
        if not project_id:
            current_project = get_project_name()
            current_id = get_project_id()
            output.print_info(f"Project: {current_project} (ID: {current_id})")
        
    else:
        # Use global session manager
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
    prompt: Optional[str] = typer.Argument(
        None,
        help="Optional prompt to continue the session with",
    ),
    transcript: bool = typer.Option(
        False,
        "--transcript",
        help="Only show the session transcript instead of restoring state",
    ),
):
    """Resume a session with full conversational state restored."""
    output = get_output_controller()

    # Transcript-only path (opt-in for the old behaviour).
    if transcript:
        _print_session_transcript(session_id, output)
        return

    # Deterministic restoration via the shared rehydrate helper.
    from ..session.resume import rehydrate_session

    restored = rehydrate_session(session_id)

    if not restored.found:
        output.print_error(
            f"Session not found: {session_id}",
            remediation="Use 'praisonai session list' to see available sessions"
        )
        raise typer.Exit(1)

    # When a prompt is supplied we hand off to `_run_prompt`, which owns all
    # output for the continuation run. Emitting a restore blob here too would
    # produce two top-level outputs (and break `--json` consumers), so we skip
    # the standalone restore rendering in that case.
    if prompt is None:
        if output.is_json_mode:
            output.print_json({
                "session": restored.to_dict(),
                "restored": True,
            })
            return

        output.print_panel(
            f"Session: {restored.agent_name or restored.session_id}\n"
            f"Model: {restored.model or 'default'}\n"
            f"Messages restored: {len(restored.chat_history)}",
            title="Session Resumed"
        )

        if restored.chat_history:
            output.print("\n--- Restored Conversation ---\n")
            for msg in restored.chat_history[-10:]:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                output.print(f"[{role}] {content}")
        return

    # Continue the run with the restored state via the shared run path so
    # behaviour matches `praisonai run --session <id>`.
    from .run import _run_prompt

    _run_prompt(
        prompt=prompt,
        model=restored.model,
        session=session_id,
    )


def _print_session_transcript(session_id: str, output) -> None:
    """Print a session transcript (legacy ``--transcript`` behaviour)."""
    manager = get_session_manager()
    session = manager.get(session_id)

    if not session:
        output.print_error(
            f"Session not found: {session_id}",
            remediation="Use 'praisonai session list' to see available sessions"
        )
        raise typer.Exit(1)

    events = manager.get_events(session_id)

    if output.is_json_mode:
        output.print_json({
            "session": session.to_dict(),
            "events": events,
        })
        return

    output.print_panel(
        f"Session: {session.name or session.session_id}\n"
        f"Run ID: {session.run_id}\n"
        f"Trace ID: {session.trace_id}\n"
        f"Events: {session.event_count}\n"
        f"Status: {session.status}",
        title="Session Transcript"
    )

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
