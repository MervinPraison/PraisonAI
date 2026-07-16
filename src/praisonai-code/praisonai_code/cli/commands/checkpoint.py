"""
Checkpoint command group for PraisonAI CLI.

Surfaces the core file-level checkpoint engine
(``praisonaiagents.checkpoints.CheckpointService``) as first-class CLI
commands, delegating to the existing :class:`CheckpointsHandler`.

Examples:
    praisonai checkpoint save "before refactor"
    praisonai checkpoint list
    praisonai checkpoint restore <id|last>
    praisonai checkpoint rewind [steps]
    praisonai checkpoint diff [from] [to]
    praisonai checkpoint delete
"""

import asyncio
import os
from typing import Optional

import typer

app = typer.Typer(help="File-level checkpoint management (save / restore / diff)")


def _resolve_storage_dir() -> Optional[str]:
    """Return a configured ``checkpoints.storage_dir`` if one is set.

    Threading this through keeps the standalone ``praisonai checkpoint``
    commands reading from the same store the interactive coding session
    (``code --checkpoints``) writes to. Falls back to ``None`` (the default
    store) when no config is present or it cannot be read.
    """
    try:
        from ..configuration.resolver import resolve_config

        section = (resolve_config().extra or {}).get("checkpoints", {})
        if isinstance(section, dict):
            return section.get("storage_dir")
    except Exception:
        pass
    return None


def _handler(workspace: Optional[str] = None, verbose: bool = False):
    """Build a CheckpointsHandler for the current workspace."""
    from praisonai_code.cli.features.checkpoints import CheckpointsHandler

    return CheckpointsHandler(
        workspace_dir=workspace or os.getcwd(),
        verbose=verbose,
        storage_dir=_resolve_storage_dir(),
    )


async def _resolve_checkpoint_id(handler, ref: str) -> Optional[str]:
    """Resolve a checkpoint reference (an id/short_id or the literal 'last').

    Resolution order: literal ``last``/``latest`` -> exact id/short_id ->
    unique id prefix. Ambiguous prefixes (matching more than one checkpoint)
    are rejected so a workspace-mutating restore never targets the wrong
    checkpoint.

    Returns the resolved checkpoint id, or ``None`` when no matching (or an
    ambiguous) checkpoint reference is given.
    """
    service = await handler._get_service()
    checkpoints = await service.list_checkpoints(limit=100)
    if not checkpoints:
        return None

    if ref in ("last", "latest"):
        # list_checkpoints returns newest-first.
        return checkpoints[0].id

    exact = [cp.id for cp in checkpoints if cp.id == ref or cp.short_id == ref]
    if exact:
        return exact[0]

    prefix_matches = [cp.id for cp in checkpoints if cp.id.startswith(ref)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        handler._print_error(f"Ambiguous checkpoint reference: {ref}")
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


@app.command("rewind")
def rewind(
    steps: int = typer.Argument(1, help="How many turns/checkpoints to step back (default: 1 = undo last turn)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """Rewind the workspace back N turns (default 1 = undo the last turn's file changes)."""
    handler = _handler(workspace)
    if not asyncio.run(handler.rewind(steps)):
        raise typer.Exit(1)


@app.command("diff")
def diff(
    from_id: Optional[str] = typer.Argument(None, help="Starting checkpoint (default: previous)"),
    to_id: Optional[str] = typer.Argument(None, help="Ending checkpoint (default: working directory)"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """Show the diff between checkpoints (or against the working directory)."""
    handler = _handler(workspace)

    async def _run() -> None:
        # Resolve the same references restore accepts ('last'/short id/prefix)
        # so `diff last` or `diff <short_id>` don't reach git as literal refs.
        resolved_from = (
            await _resolve_checkpoint_id(handler, from_id) if from_id else None
        )
        resolved_to = (
            await _resolve_checkpoint_id(handler, to_id) if to_id else None
        )
        if from_id and resolved_from is None:
            handler._print_error(f"No checkpoint found for: {from_id}")
            return
        if to_id and resolved_to is None:
            handler._print_error(f"No checkpoint found for: {to_id}")
            return
        await handler.diff(resolved_from, resolved_to)

    asyncio.run(_run())


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
