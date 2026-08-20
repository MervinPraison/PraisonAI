"""List registered external CLI backends.

Typer surface for the backend registry so ``praisonai backends`` works on a
standalone ``praisonai-code`` install (the legacy argparse ``backends list``
path is wrapper-resident and unreachable without the wrapper).
"""

from __future__ import annotations

import typer

app = typer.Typer(
    help="External coding-CLI backends (delegate agent turns to a CLI)",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback()
def _default(ctx: typer.Context) -> None:
    """Default action: list registered backends."""
    if ctx.invoked_subcommand is None:
        list_backends()


@app.command("list")
def list_backends() -> None:
    """List registered CLI backend ids (built-ins plus entry-point plugins)."""
    from praisonai_code.cli_backends import list_cli_backends

    for backend_id in list_cli_backends():
        typer.echo(backend_id)
