"""
Paths command group for PraisonAI CLI.

Provides path inspection:
- paths show: Display all resolved storage paths
"""

import os
from pathlib import Path

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Storage path inspection and migration")


@app.command("show")
def paths_show(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format",
    ),
):
    """
    Show all resolved storage paths.

    Displays global, project-local, and environment-overridden paths.
    """
    output = get_output_controller()

    try:
        from praisonaiagents.paths import (
            ENV_VAR,
            DEFAULT_DIR_NAME,
            LEGACY_DIR_NAME,
            get_data_dir,
            get_all_paths,
            get_project_data_dir,
        )
    except ImportError:
        output.print_error("praisonaiagents package not installed")
        raise typer.Exit(1)

    env_home = os.environ.get(ENV_VAR)
    global_dir = get_data_dir()
    project_dir = get_project_data_dir()
    legacy_dir = Path.home() / LEGACY_DIR_NAME
    all_paths = get_all_paths()

    if json_output or (hasattr(output, "is_json_mode") and output.is_json_mode):
        data = {
            "env_var": ENV_VAR,
            "env_value": env_home,
            "global_dir": str(global_dir),
            "project_dir": str(project_dir),
            "legacy_dir_exists": legacy_dir.exists(),
            "paths": {k: str(v) for k, v in all_paths.items()},
        }
        output.print_json(data)
        return

    # Text output using Rich console directly
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print("\n[bold cyan]PraisonAI Storage Paths[/bold cyan]\n")

    # Environment override
    if env_home:
        console.print(f"  [green]✓[/green] {ENV_VAR} = {env_home}")
    else:
        console.print(f"  [dim]{ENV_VAR} is not set (using defaults)[/dim]")

    console.print()

    # Table of paths
    table = Table(title="Resolved Paths", show_lines=False)
    table.add_column("Category", style="cyan")
    table.add_column("Path", style="white")
    table.add_column("Exists", justify="center")

    table.add_row(
        "Global data dir",
        str(global_dir),
        "✅" if global_dir.exists() else "—",
    )
    table.add_row(
        "Project data dir",
        str(project_dir),
        "✅" if project_dir.exists() else "—",
    )

    for name, path_val in sorted(all_paths.items()):
        p = Path(str(path_val))
        table.add_row(name, str(p), "✅" if p.exists() else "—")

    console.print(table)

    # Legacy warning
    if legacy_dir.exists():
        console.print(
            f"\n  [yellow]⚠ Legacy directory {legacy_dir} exists.[/yellow]"
        )
