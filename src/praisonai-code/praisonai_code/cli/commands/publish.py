"""
Publish command group for PraisonAI CLI.

Provides package publishing with automatic version bumping.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich import print as rprint

app = typer.Typer(help="Package publishing")


def _find_pyproject() -> Path:
    """Find pyproject.toml in current directory."""
    p = Path.cwd() / "pyproject.toml"
    if not p.exists():
        rprint("[red]Error: No pyproject.toml found in current directory[/red]")
        raise typer.Exit(1)
    return p


def _read_version(pyproject: Path) -> str:
    """Read version from pyproject.toml."""
    content = pyproject.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        rprint("[red]Error: Could not find version in pyproject.toml[/red]")
        raise typer.Exit(1)
    return match.group(1)


def _bump_version(version: str, major: bool = False, minor: bool = False) -> str:
    """Bump version string.
    
    Default bumps patch (last number): 1.5.21 -> 1.5.22
    --minor: 1.5.21 -> 1.6.0
    --major: 1.5.21 -> 2.0.0
    """
    parts = version.split(".")
    if len(parts) != 3:
        rprint(f"[red]Error: Version '{version}' is not in X.Y.Z format[/red]")
        raise typer.Exit(1)
    
    maj, min_, patch = int(parts[0]), int(parts[1]), int(parts[2])
    
    if major:
        return f"{maj + 1}.0.0"
    elif minor:
        return f"{maj}.{min_ + 1}.0"
    else:
        return f"{maj}.{min_}.{patch + 1}"


def _write_version(pyproject: Path, old_version: str, new_version: str):
    """Write new version to pyproject.toml."""
    content = pyproject.read_text()
    content = content.replace(f'version = "{old_version}"', f'version = "{new_version}"', 1)
    pyproject.write_text(content)


def _run_step(cmd: list[str], label: str, dry_run: bool = False) -> bool:
    """Run a build step, printing status."""
    cmd_str = " ".join(cmd)
    if dry_run:
        rprint(f"  [dim]→ {cmd_str}[/dim]")
        return True
    
    rprint(f"[cyan]→ {cmd_str}[/cyan]")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        rprint(f"[red]✗ {label} failed[/red]")
        if result.stderr:
            rprint(f"[red]{result.stderr.strip()}[/red]")
        if result.stdout:
            rprint(f"[dim]{result.stdout.strip()}[/dim]")
        return False
    
    if result.stdout:
        # Show concise output
        lines = result.stdout.strip().split("\n")
        for line in lines[-5:]:  # last 5 lines
            rprint(f"  [dim]{line}[/dim]")
    rprint(f"[green]✓ {label}[/green]")
    return True


@app.callback(invoke_without_command=True)
def publish_main(ctx: typer.Context):
    """
    Publish packages to registries.
    
    Use a subcommand like 'pypi' to specify the target.
    
    Examples:
        praisonai publish pypi
        praisonai publish pypi --minor
        praisonai publish pypi --dry-run
    """
    if ctx.invoked_subcommand is None:
        rprint("[yellow]Usage: praisonai publish pypi [OPTIONS][/yellow]")
        rprint("Run [bold]praisonai publish pypi --help[/bold] for options.")
        raise typer.Exit(0)


@app.command("pypi")
def publish_pypi(
    major: bool = typer.Option(False, "--major", help="Bump major version (X.0.0)"),
    minor: bool = typer.Option(False, "--minor", help="Bump minor version (X.Y.0)"),
    no_bump: bool = typer.Option(False, "--no-bump", help="Skip version increment"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would happen without executing"),
    token_var: str = typer.Option("PYPI_TOKEN", "--token-var", help="Environment variable name for PyPI token"),
):
    """
    Publish package to PyPI.
    
    Auto-increments the patch version (last number) by default,
    then runs: rm -rf dist && uv lock && uv build && uv publish
    
    Examples:
        praisonai publish pypi                  # bump patch: 1.5.21 -> 1.5.22
        praisonai publish pypi --minor          # bump minor: 1.5.21 -> 1.6.0
        praisonai publish pypi --major          # bump major: 1.5.21 -> 2.0.0
        praisonai publish pypi --no-bump        # publish without version change
        praisonai publish pypi --dry-run        # preview without executing
        praisonai publish pypi --token-var UV_PUBLISH_TOKEN
    """
    # 1. Find pyproject.toml
    pyproject = _find_pyproject()
    old_version = _read_version(pyproject)
    
    # 2. Bump version
    if no_bump:
        new_version = old_version
        rprint(f"[yellow]Skipping version bump — publishing {old_version}[/yellow]")
    else:
        if major and minor:
            rprint("[red]Error: Cannot use --major and --minor together[/red]")
            raise typer.Exit(1)
        new_version = _bump_version(old_version, major=major, minor=minor)
        bump_type = "major" if major else ("minor" if minor else "patch")
        rprint(f"[cyan]Version bump ({bump_type}): {old_version} → {new_version}[/cyan]")
    
    # 3. Get PyPI token
    token = os.environ.get(token_var)
    if not token:
        rprint(f"[red]Error: {token_var} environment variable not set[/red]")
        rprint(f"[dim]Set it with: export {token_var}=pypi-...[/dim]")
        raise typer.Exit(1)
    rprint(f"[green]✓ PyPI token found ({token_var})[/green]")
    
    # 4. Dry run summary
    if dry_run:
        rprint("\n[yellow]Dry run — no changes will be made:[/yellow]")
        if not no_bump:
            rprint(f"  [dim]→ Update pyproject.toml: {old_version} → {new_version}[/dim]")
        _run_step(["rm", "-rf", "dist"], "clean", dry_run=True)
        _run_step(["uv", "lock"], "lock", dry_run=True)
        _run_step(["uv", "build"], "build", dry_run=True)
        _run_step(["uv", "publish", "--token", f"${token_var}"], "publish", dry_run=True)
        rprint("[green]Dry run complete.[/green]")
        return
    
    # 5. Write new version
    if not no_bump:
        _write_version(pyproject, old_version, new_version)
        rprint(f"[green]✓ Updated pyproject.toml[/green]")
    
    # 6. Clean dist
    dist_dir = Path.cwd() / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    rprint("[green]✓ Cleaned dist/[/green]")
    
    # 7. uv lock
    if not _run_step(["uv", "lock"], "uv lock"):
        raise typer.Exit(1)
    
    # 8. uv build
    if not _run_step(["uv", "build"], "uv build"):
        raise typer.Exit(1)
    
    # 9. uv publish
    if not _run_step(["uv", "publish", "--token", token], "uv publish"):
        raise typer.Exit(1)
    
    rprint(f"\n[bold green]✓ Published {new_version} to PyPI[/bold green]")
