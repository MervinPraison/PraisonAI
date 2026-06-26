"""
Checkpoint command group for PraisonAI CLI.

Surfaces the core file-level checkpoint engine
(``praisonaiagents.checkpoints.CheckpointService``) as first-class CLI
commands, delegating to the existing :class:`CheckpointsHandler`.

Examples:
    praisonai checkpoint save "before refactor"
    praisonai checkpoint list
    praisonai checkpoint restore <id|last>
    praisonai checkpoint diff [from] [to]
    praisonai checkpoint delete
"""

import asyncio
import os
from typing import Optional

import typer

app = typer.Typer(help="File-level checkpoint management (save / restore / diff)")


def _handler(workspace: Optional[str] = None, verbose: bool = False):
    """Build a CheckpointsHandler for the current workspace."""
    from ..features.checkpoints import CheckpointsHandler

    return CheckpointsHandler(workspace_dir=workspace or os.getcwd(), verbose=verbose)


async def _resolve_checkpoint_id(handler, ref: str) -> Optional[str]:
    """Resolve a checkpoint reference (an id/short_id or the literal 'last').

    Returns the resolved checkpoint id, or ``None`` when no matching
    checkpoint exists.
    """
    service = await handler._get_service()
    checkpoints = await service.list_checkpoints(limit=100)
    if not checkpoints:
        return None

    if ref in ("last", "latest"):
        # list_checkpoints returns newest-first.
        return checkpoints[0].id

    for cp in checkpoints:
        if cp.id == ref or cp.id.startswith(ref) or cp.short_id == ref:
            return cp.id
    return None


@app.command("save")
def save(
    message: str = typer.Argument(..., help="Checkpoint message"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Allow checkpoint with no changes"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """Save a checkpoint of the current workspace."""
    handler = _handler(workspace)
    ok = asyncio.run(handler.save(message, allow_empty=allow_empty))
    if not ok:
        raise typer.Exit(1)


@app.command("list")
def list_checkpoints(
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum checkpoints to show"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """List checkpoints for the workspace (newest first)."""
    handler = _handler(workspace)
    asyncio.run(handler.list_checkpoints(limit=limit))


@app.command("restore")
def restore(
    checkpoint_id: str = typer.Argument(..., help="Checkpoint id, short id, or 'last'"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """Restore the workspace to a checkpoint (accepts 'last')."""
    handler = _handler(workspace)

    async def _run() -> bool:
        resolved = await _resolve_checkpoint_id(handler, checkpoint_id)
        if resolved is None:
            handler._print_error(f"No checkpoint found for: {checkpoint_id}")
            return False
        return await handler.restore(resolved)

    if not asyncio.run(_run()):
        raise typer.Exit(1)


@app.command("diff")
def diff(
    from_id: Optional[str] = typer.Argument(None, help="Starting checkpoint (default: previous)"),
    to_id: Optional[str] = typer.Argument(None, help="Ending checkpoint (default: working directory)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """Show the diff between checkpoints (or against the working directory)."""
    handler = _handler(workspace)
    asyncio.run(handler.diff(from_id, to_id))


@app.command("delete")
def delete(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """Delete all checkpoints for the workspace."""
    handler = _handler(workspace)
    if not yes and not typer.confirm("Delete all checkpoints?"):
        typer.echo("Cancelled")
        return
    ok = asyncio.run(handler.delete_all())
    if not ok:
        raise typer.Exit(1)
