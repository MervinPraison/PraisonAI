"""``praisonai upgrade`` — self-update the managed CLI install.

Updates the PraisonAI CLI in place using whichever tool manager provisioned it
(``uv tool`` / ``pipx`` for the one-line installer, or ``pip`` for library
installs). ``--check`` reports whether a newer release exists without mutating
anything. This is CLI self-management only; ``praisonaiagents`` is untouched.
"""

import subprocess

import typer

from ..output.console import get_output_controller
from ..features.self_manage import (
    detect_install,
    get_installed_version,
    get_latest_version,
    is_newer,
    refresh_update_cache,
)

app = typer.Typer(help="Update the managed PraisonAI CLI install")


@app.callback(invoke_without_command=True)
def upgrade(
    ctx: typer.Context,
    check: bool = typer.Option(
        False,
        "--check",
        help="Report whether a newer version exists without upgrading.",
    ),
):
    """Update PraisonAI in place, or check for a newer release with ``--check``."""
    if ctx.invoked_subcommand is not None:
        return

    output = get_output_controller()
    current = get_installed_version()

    if check:
        latest = get_latest_version()
        # Warm the background-hint cache so long-lived installs surface the
        # notice on next start without their own network round-trip.
        refresh_update_cache()
        if latest is None:
            if output.is_json_mode:
                output.print_json(
                    {"current": current, "latest": None, "update_available": None,
                     "error": "Could not reach PyPI"}
                )
            else:
                output.print_error("Could not check for updates (network error).")
                output.print(f"Current version: {current}")
            raise typer.Exit(1)

        available = is_newer(latest, current)
        if output.is_json_mode:
            output.print_json(
                {"current": current, "latest": latest, "update_available": available}
            )
        elif available:
            output.print_warning(
                f"Update available: {current} -> {latest}\nRun: praisonai upgrade"
            )
        else:
            output.print_success(f"You are on the latest version ({current}).")
        return

    info = detect_install()
    if info.upgrade_cmd is None:
        output.print_error(
            f"Automatic upgrade is not supported for a '{info.manager}' install.\n"
            "Upgrade manually with: pip install --upgrade praisonai"
        )
        raise typer.Exit(1)

    if not output.is_json_mode:
        output.print(
            f"Upgrading PraisonAI via {info.manager}: {' '.join(info.upgrade_cmd)}"
        )

    try:
        result = subprocess.run(info.upgrade_cmd)
    except Exception as e:  # pragma: no cover - defensive
        output.print_error(f"Upgrade failed: {e}")
        raise typer.Exit(1)

    if result.returncode != 0:
        output.print_error(
            f"Upgrade command exited with code {result.returncode}."
        )
        raise typer.Exit(result.returncode)

    new_version = get_installed_version()
    if output.is_json_mode:
        output.print_json(
            {"manager": info.manager, "previous": current, "current": new_version}
        )
    else:
        output.print_success(
            f"PraisonAI upgraded ({current} -> {new_version})."
            if new_version != current
            else f"PraisonAI is up to date ({new_version})."
        )
