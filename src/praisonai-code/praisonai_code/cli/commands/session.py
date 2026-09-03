"""
Session command group for PraisonAI CLI.

Provides session management:
- session list: List all sessions
- session resume: Resume a session
- session delete: Delete a session
- session export: Export a session
- session share: Publish a redacted, read-only transcript and return a link
- session unshare: Revoke a previously published transcript
"""

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Optional

import typer

from ..output.console import get_output_controller
from ..state.sessions import get_session_manager, set_session_backend

app = typer.Typer(help="Session management")


def _create_backend(backend_type: str, storage_path: Optional[str]):
    """Create storage backend from CLI options.

    Defaults anchor under the *canonical* data home (``get_sessions_dir()`` →
    ``~/.praisonai/sessions``) rather than the legacy ``~/.praison`` root, so a
    backend-selected store lives under the same home as the project/global
    stores instead of silently splitting sessions across two home roots
    (Issue #3201).
    """
    try:
        from praisonaiagents.paths import get_data_dir, get_sessions_dir

        if backend_type == "file":
            from praisonaiagents.storage import FileBackend
            return FileBackend(storage_dir=storage_path or str(get_sessions_dir()))
        elif backend_type == "sqlite":
            from praisonaiagents.storage import SQLiteBackend
            db_path = storage_path or str(get_data_dir() / "sessions.db")
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
        from ..state.project_sessions import (
            get_project_session_store,
            list_project_sessions,
        )
        from ..utils.project import (
            get_project_id,
            get_project_identity_source,
            get_project_name,
        )

        # List sessions for specific or current project. For the current
        # project, merge the project-scoped and global default stores so the
        # listing matches what `--continue`/`resume` can actually see
        # (Issue #2655). A specific `--project` id stays project-scoped.
        if project_id:
            project_store = get_project_session_store(project_id=project_id)
            sessions_data = project_store.list_sessions(limit=limit)
        else:
            sessions_data = list_project_sessions(limit=limit)
        
        # Convert to expected format
        class SessionInfo:
            def __init__(self, data):
                from datetime import datetime
                
                self.session_id = data.get("session_id", data.get("id", ""))
                # Prefer a human-readable title set via `session rename` /
                # `/rename` (Issue #3737); fall back to the agent name.
                self.name = data.get("title") or data.get("agent_name", "")
                self.status = data.get("status")  # Use actual status from data if available
                self.event_count = data.get("message_count", 0)

                # Fork lineage: parent id may live at the top level or in
                # metadata depending on the store that wrote the session.
                metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
                self.parent_id = (
                    data.get("parent_id")
                    or (metadata or {}).get("parent_id")
                    or (metadata or {}).get("parent_session_id")
                )

                # Cumulative usage totals persisted per session (Issue #2421).
                usage = data.get("usage")
                if isinstance(usage, dict):
                    self.total_tokens = usage.get("total_tokens") or 0
                    self.cost = usage.get("cost") or 0.0
                else:
                    self.total_tokens = data.get("total_tokens") or 0
                    self.cost = data.get("cost") or 0.0

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
                    "total_tokens": self.total_tokens,
                    "cost": self.cost,
                    "updated_at": self.updated_at.isoformat(),
                    "parent_id": self.parent_id,
                }
        
        sessions = [SessionInfo(data) for data in sessions_data]
        
        # Add project info to output
        if not project_id:
            current_project = get_project_name()
            current_id = get_project_id()
            identity_source = get_project_identity_source()
            output.print_info(
                f"Project: {current_project} (ID: {current_id}, identity: {identity_source})"
            )
        
    else:
        # Use global session manager
        # Configure backend if specified
        if storage_backend:
            backend = _create_backend(storage_backend, storage_path)
            if backend:
                set_session_backend(backend)
        
        manager = get_session_manager()
        sessions = manager.list(limit=limit)

        # SessionMetadata objects don't carry usage; surface persisted totals
        # for global/backend listings the same way the project path does so the
        # Tokens/Cost columns aren't blank when usage was recorded (Issue #2421).
        try:
            from ..state.project_sessions import read_session_usage

            for s in sessions:
                sid = getattr(s, "session_id", None) or getattr(s, "id", None)
                if not sid:
                    continue
                usage = read_session_usage(sid)
                if usage.get("total_tokens") or usage.get("cost"):
                    try:
                        s.total_tokens = usage.get("total_tokens") or 0
                        s.cost = usage.get("cost") or 0.0
                    except Exception:
                        pass
        except Exception:
            pass

    if output.is_json_mode:
        def _session_dict(s):
            d = s.to_dict()
            # Ensure usage totals surface in JSON even for SessionMetadata,
            # whose to_dict() omits them (Issue #2421).
            if "total_tokens" not in d:
                d["total_tokens"] = getattr(s, "total_tokens", 0) or 0
            if "cost" not in d:
                d["cost"] = getattr(s, "cost", 0.0) or 0.0
            return d

        output.print_json({
            "sessions": [_session_dict(s) for s in sessions]
        })
        return
    
    if not sessions:
        output.print_info("No sessions found")
        return
    
    headers = ["ID", "Name", "Status", "Events", "Tokens", "Cost", "Parent", "Updated"]
    rows = []
    for s in sessions:
        total_tokens = getattr(s, "total_tokens", 0) or 0
        cost = getattr(s, "cost", 0.0) or 0.0
        parent_id = getattr(s, "parent_id", None)
        parent_cell = (parent_id[:8] if parent_id else "-")
        rows.append([
            s.session_id[:20] + "..." if len(s.session_id) > 20 else s.session_id,
            s.name or "-",
            s.status,
            str(s.event_count),
            f"{int(total_tokens):,}" if total_tokens else "-",
            f"${float(cost):.4f}" if cost else "-",
            parent_cell,
            s.updated_at.strftime("%Y-%m-%d %H:%M"),
        ])
    
    output.print_table(headers, rows, title="Sessions")


@app.command("search")
def session_search(
    query: str = typer.Argument(..., help="Free-text query to search transcripts"),
    limit: int = typer.Option(
        5,
        "--limit",
        "-n",
        help="Maximum number of matching sessions to return",
    ),
    window: int = typer.Option(
        5,
        "--window",
        "-w",
        help="Number of messages to include around each hit",
    ),
):
    """Ranked full-text search across session transcripts.

    Delegates to :class:`SqliteSessionStore` so results are ranked by FTS5/bm25
    with snippets and lineage dedup, reusing the same engine as the
    ``session_search`` agent tool instead of a substring scan.
    """
    output = get_output_controller()

    from praisonaiagents.session import SqliteSessionStore

    from ..state.project_sessions import canonical_cli_stores

    seen_dirs = set()
    hits = []
    for store in canonical_cli_stores():
        session_dir = getattr(store, "session_dir", None)
        if not session_dir or session_dir in seen_dirs:
            continue
        seen_dirs.add(session_dir)
        try:
            indexed = SqliteSessionStore(session_dir=session_dir)
            hits.extend(indexed.search(query, limit=limit, window=window))
        except Exception:
            continue

    # A session resumed from the global default store keeps a project-side
    # shadow, so the *same* id can match in both canonical stores. Without
    # dedup those duplicate rows each consume a slot of the small ``limit`` and
    # crowd out distinct sessions (Issue #4701). Collapse by session id, keeping
    # the higher-scoring copy, mirroring the lineage dedup the store already
    # applies within a single directory.
    best_by_id = {}
    for h in hits:
        sid = getattr(h, "session_id", None)
        if sid is None:
            continue
        existing = best_by_id.get(sid)
        if existing is None or getattr(h, "score", 0.0) > getattr(existing, "score", 0.0):
            best_by_id[sid] = h
    hits = list(best_by_id.values())

    hits.sort(key=lambda h: (getattr(h, "score", 0.0), getattr(h, "when", "") or ""), reverse=True)
    hits = hits[:limit]

    if output.is_json_mode:
        output.print_json(
            {"query": query, "results": [h.as_dict() for h in hits]}
        )
        return

    if not hits:
        output.print_info(f"No sessions matched: {query}")
        return

    headers = ["ID", "Title", "Score", "Snippet", "When"]
    rows = []
    for h in hits:
        sid = h.session_id
        rows.append([
            sid[:20] + "..." if len(sid) > 20 else sid,
            (h.title or "-")[:40],
            f"{h.score:.1f}",
            (h.snippet or "-")[:60],
            (h.when or "-")[:19],
        ])
    output.print_table(headers, rows, title=f"Search: {query}")


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

        from ..state.project_sessions import format_usage_footer

        usage_line = ""
        if restored.usage and (restored.usage.get("total_tokens") or restored.usage.get("cost")):
            usage_line = f"\nUsage: {format_usage_footer(restored.usage)}"

        output.print_panel(
            f"Session: {restored.agent_name or restored.session_id}\n"
            f"Model: {restored.model or 'default'}\n"
            f"Messages restored: {len(restored.chat_history)}"
            f"{usage_line}",
            title="Session Resumed"
        )

        if restored.chat_history:
            output.print("\n--- Restored Conversation ---\n")
            limit = 20
            total = len(restored.chat_history)
            shown = restored.chat_history[-limit:] if total > limit else restored.chat_history
            if total > len(shown):
                output.print(f"… {total - len(shown)} earlier turns\n")
            for msg in shown:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if not content:
                    tool_calls = msg.get("tool_calls")
                    if isinstance(tool_calls, list) and tool_calls:
                        names = ", ".join(
                            (tc.get("function", {}) or {}).get("name", "tool")
                            for tc in tool_calls
                            if isinstance(tc, dict)
                        )
                        content = f"[tool call] {names}" if names else "[tool call]"
                    else:
                        continue
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


@app.command("fork")
def session_fork(
    session_id: str = typer.Argument(..., help="Session ID to fork from"),
    at_message: Optional[int] = typer.Option(
        None,
        "--at-message",
        help="Fork from this 0-based message index (default: full history)",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        help="Optional title for the forked session",
    ),
):
    """Fork a session into a new child session, keeping both timelines.

    Mirrors ``praisonai run --fork`` mid-conversation: records parent/child
    lineage via the same ``HierarchicalSessionStore.fork_session`` substrate so
    both the original and the fork remain listable and resumable.
    """
    output = get_output_controller()

    from ..state.project_sessions import session_exists_anywhere

    if not session_exists_anywhere(session_id):
        output.print_error(
            f"Session not found: {session_id}",
            remediation="Use 'praisonai session list' to see available sessions",
        )
        raise typer.Exit(1)

    from praisonaiagents.session.hierarchy import HierarchicalSessionStore
    from ..utils.project import get_project_sessions_dir
    from ..state.project_sessions import canonical_cli_stores

    # A session may live in the project-scoped store or the global default
    # store (e.g. created by the gateway/TUI). Point the hierarchical store at
    # the directory that actually holds the session so a global-only session
    # forks its real history instead of producing an empty fork. Resolve the
    # directory from the *same* canonical stores ``session_exists_anywhere``
    # searched (project first, then global) so the fork source and the
    # existence check stay consistent.
    #
    # The store persists each session under a *sanitized* filename
    # (``DefaultSessionStore._get_session_path`` replaces any char that is not
    # alphanumeric/``-``/``_`` with ``_``). Sanitize identically here so a
    # global-only id containing e.g. ``.`` or ``:`` still matches its real file
    # instead of falling through to an empty project-scoped fork.
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    store_dir = str(get_project_sessions_dir())
    for candidate in canonical_cli_stores():
        candidate_dir = getattr(candidate, "session_dir", None)
        if not candidate_dir:
            continue
        if (Path(candidate_dir) / f"{safe_id}.json").exists():
            store_dir = str(candidate_dir)
            break

    store = HierarchicalSessionStore(store_dir)

    # Reject an out-of-range ``--at-message`` up front. Without this a negative
    # index selects an unintended slice and an oversized one silently copies the
    # whole history while still reporting success (Python slice semantics).
    if at_message is not None:
        parent = store._load_extended_session(session_id, force_reload=True)
        message_count = len(getattr(parent, "messages", []) or [])
        if at_message < 0 or at_message >= message_count:
            output.print_error(
                f"--at-message {at_message} is out of range "
                f"(session has {message_count} messages, valid 0..{max(message_count - 1, 0)})",
                remediation="Choose a 0-based index within the session's message range",
            )
            raise typer.Exit(1)

    forked_id = store.fork_session(
        session_id,
        from_message_index=at_message,
        title=title,
    )

    if output.is_json_mode:
        output.print_json({
            "forked": True,
            "parent_id": session_id,
            "session_id": forked_id,
            "from_message_index": at_message,
            "title": title,
        })
        return

    output.print_success(f"Forked session: {session_id} -> {forked_id}")
    output.print_info(
        f"Resume the fork with: praisonai session resume {forked_id}"
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

    # Resolve against the same stores used by list/resume/--continue so any
    # id a user can list or resume is also deletable (Issue #3133).
    from ..state.session_resolver import delete_session as _delete_session
    from ..state.session_resolver import resolve_session

    session = resolve_session(session_id)

    if not session.found:
        output.print_error(f"Session not found: {session_id}")
        raise typer.Exit(1)
    
    if not confirm:
        confirmed = typer.confirm(f"Delete session {session_id}?")
        if not confirmed:
            output.print_info("Cancelled")
            raise typer.Exit(0)
    
    deleted = _delete_session(session_id)
    
    if output.is_json_mode:
        output.print_json({"deleted": deleted, "session_id": session_id})
    else:
        if deleted:
            output.print_success(f"Deleted session: {session_id}")
        else:
            output.print_error(f"Failed to delete session: {session_id}")
            raise typer.Exit(1)


@app.command("rename")
def session_rename(
    session_id: str = typer.Argument(..., help="Session ID to rename"),
    title: str = typer.Argument(..., help="New human-readable title"),
):
    """Give a session a human-readable title (Issue #3737).

    Sessions are otherwise addressable only by opaque id; a title makes
    ``praisonai session list`` and ``/sessions`` readable at a glance.
    """
    output = get_output_controller()

    from ..state.session_resolver import rename_session as _rename_session
    from ..state.session_resolver import resolve_session

    session = resolve_session(session_id)
    if not session.found:
        output.print_error(
            f"Session not found: {session_id}",
            remediation="Use 'praisonai session list' to see available sessions",
        )
        raise typer.Exit(1)

    renamed = _rename_session(session_id, title)

    if output.is_json_mode:
        output.print_json(
            {"renamed": renamed, "session_id": session_id, "title": title}
        )
        return

    if renamed:
        output.print_success(f"Renamed session {session_id} to: {title}")
    else:
        output.print_error(f"Failed to rename session: {session_id}")
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
    sanitise: bool = typer.Option(
        False,
        "--sanitise",
        "--sanitize",
        help=(
            "Redact secrets, absolute paths, the working directory, and "
            "embedded file contents with stable placeholders before export "
            "(opt-in; default export is unchanged)."
        ),
    ),
    redact_level: str = typer.Option(
        "standard",
        "--redact-level",
        help="Redaction level when --sanitise is set: 'standard' or 'strict'.",
    ),
):
    """Export a session."""
    output = get_output_controller()

    # Export the same session id list/resume expose (Issue #3133).
    from ..state.session_resolver import export_session
    from ..state.redact import REDACT_LEVELS

    if redact_level not in REDACT_LEVELS:
        output.print_error(
            f"Invalid --redact-level '{redact_level}'. "
            f"Choose one of: {', '.join(REDACT_LEVELS)}."
        )
        raise typer.Exit(1)

    content = export_session(
        session_id,
        format=format,
        redact=sanitise,
        redact_level=redact_level,
    )

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
    recap: bool = typer.Option(
        False,
        "--recap",
        help=(
            "Render a read-only 'where were we' summary of the session instead "
            "of raw details (does not mutate the session or trigger compaction)."
        ),
    ),
):
    """Show session details."""
    output = get_output_controller()

    # Resolve against the same stores used by list/resume/--continue so any
    # id a user can list or resume is also showable (Issue #3133).
    from ..state.session_resolver import resolve_session

    session = resolve_session(session_id)

    if not session.found:
        output.print_error(f"Session not found: {session_id}")
        raise typer.Exit(1)

    # Read-only recap: reuse the shared summariser purely to inform the user.
    if recap:
        from praisonaiagents.compaction import build_recap

        recap_text = build_recap(session.chat_history or [])
        if output.is_json_mode:
            output.print_json({"session_id": session.session_id, "recap": recap_text})
            return
        output.print_panel(recap_text, title="Session Recap")
        return

    if output.is_json_mode:
        output.print_json(session.to_dict())
        return
    
    output.print_panel(
        f"Session ID: {session.session_id}\n"
        f"Agent: {session.agent_name or '-'}\n"
        f"Model: {session.model or '-'}\n"
        f"Created: {session.created_at or '-'}\n"
        f"Updated: {session.updated_at or '-'}\n"
        f"Messages: {session.message_count}",
        title="Session Details"
    )


@app.command("handoff")
def session_handoff(
    session_id: Optional[str] = typer.Argument(
        None,
        help="Session ID to hand off (default: most recent session)",
    ),
    copy: bool = typer.Option(
        False,
        "--copy",
        help="Copy the continuation prompt to the clipboard (best-effort).",
    ),
):
    """Print a self-contained continuation prompt assembled from durable state.

    Unlike ``resume`` (which restores conversation) this is an additive,
    read-only surface: it turns already-persisted goal/workflow/recap state into
    the one artifact a fresh context needs — a generated continuation prompt —
    without an LLM call.
    """
    output = get_output_controller()

    # Default to the most recent session when no id is given, mirroring the
    # "most recent session" default the issue asks for.
    if session_id is None:
        try:
            from ..state.project_sessions import list_project_sessions

            recent = list_project_sessions(limit=1)
        except Exception:
            recent = []
        if not recent:
            output.print_error(
                "No sessions found",
                remediation="Start a session first, or pass a session id",
            )
            raise typer.Exit(1)
        session_id = recent[0].get("session_id") or recent[0].get("id")

    from ..state.session_resolver import resolve_session

    session = resolve_session(session_id)
    if not session.found:
        output.print_error(
            f"Session not found: {session_id}",
            remediation="Use 'praisonai session list' to see available sessions",
        )
        raise typer.Exit(1)

    from praisonaiagents.compaction import build_recap
    from praisonaiagents.session import build_handoff_prompt

    chat_history = session.chat_history or []
    recap_text = build_recap(chat_history) if chat_history else ""
    goal_state = (session.metadata or {}).get("goal_state")
    checkpoint = (session.metadata or {}).get("workflow_checkpoint")

    prompt = build_handoff_prompt(
        recap=recap_text,
        goal_state=goal_state if isinstance(goal_state, dict) else None,
        workflow_checkpoint=checkpoint if isinstance(checkpoint, dict) else None,
    )

    if output.is_json_mode:
        output.print_json(
            {
                "session_id": session_id,
                "handoff": prompt,
                "has_goal": isinstance(goal_state, dict),
                "has_checkpoint": isinstance(checkpoint, dict),
            }
        )
        return

    if copy:
        try:
            import pyperclip  # type: ignore

            pyperclip.copy(prompt)
            output.print_info("Continuation prompt copied to clipboard.")
        except Exception:
            output.print_info("Clipboard unavailable; printing prompt instead.")

    output.print_panel(prompt, title="Session Handoff")


def _shares_dir() -> Path:
    """Directory holding published transcripts (``~/.praisonai/shares``).

    Lives under the canonical data home so shares sit alongside the session
    stores rather than a second home root (consistent with #3201).
    """
    from praisonaiagents.paths import get_data_dir

    path = get_data_dir() / "shares"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _share_path(session_id: str) -> Path:
    """Stable per-session transcript path (id hashed to a safe filename)."""
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
    return _shares_dir() / f"{digest}.html"


def _render_share_html(session_id: str, transcript_md: str) -> str:
    """Wrap an already-redacted Markdown transcript in a self-contained page.

    Zero external infrastructure: a single static HTML file that opens over
    ``file://``. The transcript is inserted as pre-escaped text so no session
    content is interpreted as markup.
    """
    from html import escape

    body = escape(transcript_md)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>PraisonAI session {escape(session_id)}</title>\n"
        "<style>body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;"
        "max-width:860px;margin:2rem auto;padding:0 1rem;color:#1b1f24}"
        "pre{white-space:pre-wrap;word-wrap:break-word}"
        ".note{color:#57606a;font-size:12px;margin-bottom:1rem}</style>\n"
        "</head>\n<body>\n"
        '<p class="note">Read-only shared transcript · best-effort secret '
        "redaction applied — review before sharing widely</p>\n"
        f"<pre>{body}</pre>\n"
        "</body>\n</html>\n"
    )


@app.command("share")
def session_share(
    session_id: str = typer.Argument(..., help="Session ID to share"),
    redact_level: str = typer.Option(
        "strict",
        "--redact-level",
        help="Redaction level: 'standard' or 'strict'. Defaults to 'strict' "
        "because share publishes a transcript for wider distribution.",
    ),
):
    """Publish a redacted, read-only transcript and return a shareable link.

    Reuses the existing session resolver + transcript redactor (#3426), then
    writes a single self-contained HTML file to ``~/.praisonai/shares`` and
    returns a ``file://`` link — no external service or dependency required.
    Sharing is opt-in and applies best-effort secret redaction first; review
    the published transcript before sharing it widely.
    """
    output = get_output_controller()

    from ..state.redact import REDACT_LEVELS
    from ..state.session_resolver import export_session

    if redact_level not in REDACT_LEVELS:
        output.print_error(
            f"Invalid --redact-level '{redact_level}'. "
            f"Choose one of: {', '.join(REDACT_LEVELS)}."
        )
        raise typer.Exit(1)

    transcript = export_session(
        session_id,
        format="md",
        redact=True,
        redact_level=redact_level,
    )

    if transcript is None:
        output.print_error(
            f"Session not found: {session_id}",
            remediation="Use 'praisonai session list' to see available sessions",
        )
        raise typer.Exit(1)

    try:
        share_path = _share_path(session_id)
        rendered_html = _render_share_html(session_id, transcript)
        # Write to a sibling temp file then atomically replace, so a failed or
        # interrupted write never truncates a previously published transcript.
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=share_path.parent,
                prefix=f".{share_path.stem}-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temp_path = Path(temporary_file.name)
                temporary_file.write(rendered_html)
            os.replace(temp_path, share_path)
        except OSError:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise
    except OSError as e:
        output.print_error(f"Failed to share session: {e}")
        raise typer.Exit(1) from e

    url = share_path.resolve().as_uri()

    if output.is_json_mode:
        output.print_json({
            "session_id": session_id,
            "shared": True,
            "url": url,
            "path": str(share_path),
        })
        return

    output.print_success(f"Shared session: {session_id}")
    output.print_info(f"Link: {url}")


@app.command("unshare")
def session_unshare(
    session_id: str = typer.Argument(..., help="Session ID to unshare"),
):
    """Revoke a previously published transcript."""
    output = get_output_controller()

    revoked = False
    try:
        share_path = _share_path(session_id)
        # Unlink unconditionally: a missing file is a successful no-op and races
        # with a concurrent deletion are treated as already-revoked.
        share_path.unlink()
        revoked = True
    except FileNotFoundError:
        revoked = False
    except OSError as e:
        output.print_error(f"Failed to unshare session: {e}")
        raise typer.Exit(1) from e

    if output.is_json_mode:
        output.print_json({"session_id": session_id, "revoked": revoked})
        return

    if revoked:
        output.print_success(f"Unshared session: {session_id}")
    else:
        output.print_info(f"No shared transcript found for: {session_id}")


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
        from praisonai_code.cli.interactive import InteractiveCore
        
        core = InteractiveCore()
        session_id = core.import_session(data)
        
        if output.is_json_mode:
            output.print_json({"imported": True, "session_id": session_id})
        else:
            output.print_success(f"Imported session: {session_id}")
            
    except Exception as e:
        output.print_error(f"Import failed: {e}")
        raise typer.Exit(1)
