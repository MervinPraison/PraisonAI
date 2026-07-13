"""``praisonai uninstall`` — cleanly remove the managed CLI install.

Removes the managed PraisonAI environment and global shim provisioned by the
one-line installer (``uv tool`` / ``pipx``), or uninstalls the ``pip`` package
for library installs. CLI self-management only; ``praisonaiagents`` is not
touched by this command.
"""

import subprocess

import typer

from ..output.console import get_output_controller
from ..features.self_manage import detect_install, get_installed_version

app = typer.Typer(help="Remove the managed PraisonAI CLI install")


@app.callback(invoke_without_command=True)
def uninstall(
    ctx: typer.Context,
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the confirmation prompt (non-interactive/CI).",
    ),
):
    """Remove the managed PraisonAI environment and global ``praisonai`` shim."""
    if ctx.invoked_subcommand is not None:
        return

    output = get_output_controller()
    info = detect_install()
    current = get_installed_version()

    if info.uninstall_cmd is None:
        output.print_error(
            f"Automatic uninstall is not supported for a '{info.manager}' install.\n"
            "Remove manually with: pip uninstall praisonai"
        )
        raise typer.Exit(1)

    if not yes and not output.is_json_mode:
        confirmed = typer.confirm(
            f"Remove PraisonAI {current} (installed via {info.manager})?"
        )
        if not confirmed:
            output.print("Uninstall cancelled.")
            raise typer.Exit(0)

    if not output.is_json_mode:
        output.print(
            f"Uninstalling PraisonAI via {info.manager}: "
            f"{' '.join(info.uninstall_cmd)}"
        )

    try:
        result = subprocess.run(info.uninstall_cmd)
    except Exception as e:  # pragma: no cover - defensive
        output.print_error(f"Uninstall failed: {e}")
        raise typer.Exit(1)

    if result.returncode != 0:
        output.print_error(
            f"Uninstall command exited with code {result.returncode}."
        )
        raise typer.Exit(result.returncode)

    if output.is_json_mode:
        output.print_json({"manager": info.manager, "removed": current})
    else:
        output.print_success(f"PraisonAI {current} removed.")
