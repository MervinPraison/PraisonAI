"""
Doctor command group for PraisonAI CLI.

Wraps existing doctor functionality from features/doctor/.
Provides health checks and diagnostics.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Health checks and diagnostics")


@app.callback(invoke_without_command=True)
def doctor_main(
    ctx: typer.Context,
    quick: bool = typer.Option(False, "--quick", help="Fast env-only checks (alias for 'doctor env')"),
    live: bool = typer.Option(False, "--live", help="Include live provider pings (validate keys, not just presence)"),
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures"),
    json_output: bool = typer.Option(False, "--json", help="Output machine-readable JSON"),
):
    """Run a full setup report when no subcommand is given.

    ``praisonai doctor`` (no subcommand) now runs a comprehensive first-run /
    operator troubleshooting report instead of failing with "Missing command".
    Use ``praisonai doctor env`` (or ``--quick``) for the fast, CI-friendly path.
    """
    if ctx.invoked_subcommand is not None:
        return

    args: list = []
    if quick:
        args.append("env")
    if live:
        args.append("--live")
    if deep:
        args.append("--deep")
    if strict:
        args.append("--strict")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


def _run_doctor(args: list) -> int:
    """Run doctor command with args."""
    try:
        from praisonai_code.cli.features.doctor.handler import DoctorHandler
        handler = DoctorHandler()
        # DoctorHandler uses execute(action, action_args) pattern
        action = args[0] if args else None
        action_args = args[1:] if len(args) > 1 else []
        return handler.execute(action, action_args)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Doctor module not available: {e}")
        return 4
    except Exception as e:
        output = get_output_controller()
        output.print_error(f"Doctor command failed: {e}")
        return 1


@app.command("env")
def doctor_env(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check environment variables."""
    args = ["env"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("docker")
def doctor_docker(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check Docker installation and configuration."""
    args = ["docker"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("llm-providers")
def doctor_llm_providers(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check LLM providers configuration."""
    args = ["llm-providers"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("memory-store")
def doctor_memory_store(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check memory store backends."""
    args = ["memory-store"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("metadata-store")
def doctor_metadata_store(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check metadata store configuration."""
    args = ["metadata-store"]
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("mcp")
def doctor_mcp(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check MCP server connectivity and health."""
    args = ["mcp"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("network")
def doctor_network(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check network connectivity."""
    args = ["network"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("packaging")
def doctor_packaging(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check packaging and entry point configuration (Windows daemon compatibility)."""
    args = ["packaging"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("performance")
def doctor_performance(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check performance metrics."""
    args = ["performance"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("selftest")
def doctor_selftest(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Run self-test."""
    args = ["selftest"]
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("cleanup")
def doctor_cleanup(
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Show what would be removed without removing"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Clean up stale package artifacts that can cause import errors.
    
    This removes stale praisonaiagents directories from site-packages that
    lack an __init__.py file (namespace package artifacts).
    
    Examples:
        praisonai doctor cleanup           # Show what would be removed
        praisonai doctor cleanup --execute # Actually remove stale artifacts
    """
    import os
    import site
    import shutil
    
    output = get_output_controller()
    
    stale_dirs = []
    
    # Check all site-packages directories
    try:
        site_packages = site.getsitepackages()
    except AttributeError:
        site_packages = []
    
    # Also check user site-packages
    user_site = site.getusersitepackages() if hasattr(site, 'getusersitepackages') else None
    if user_site:
        site_packages = list(site_packages) + [user_site]
    
    for sp in site_packages:
        praisonai_dir = os.path.join(sp, 'praisonaiagents')
        if os.path.isdir(praisonai_dir):
            init_path = os.path.join(praisonai_dir, '__init__.py')
            if not os.path.exists(init_path):
                stale_dirs.append(praisonai_dir)
    
    if not stale_dirs:
        output.print_success("No stale package artifacts found. Environment is clean.")
        raise typer.Exit(0)
    
    output.print_warning(f"Found {len(stale_dirs)} stale praisonaiagents directory(ies):")
    for d in stale_dirs:
        output.console.print(f"  • {d}")
    
    if dry_run:
        output.console.print("\n[dim]Run with --execute to remove these directories.[/dim]")
        raise typer.Exit(0)
    
    # Confirm before removing
    if not force:
        confirm = typer.confirm("\nRemove these directories?")
        if not confirm:
            output.print_info("Aborted.")
            raise typer.Exit(0)
    
    # Remove stale directories
    removed = 0
    for d in stale_dirs:
        try:
            shutil.rmtree(d)
            output.print_success(f"Removed: {d}")
            removed += 1
        except Exception as e:
            output.print_error(f"Failed to remove {d}: {e}")
    
    if removed == len(stale_dirs):
        output.print_success(f"\nSuccessfully cleaned up {removed} stale directory(ies).")
        output.console.print("[dim]Run 'pip install praisonaiagents' to reinstall if needed.[/dim]")
    else:
        output.print_warning(f"\nCleaned up {removed}/{len(stale_dirs)} directories.")
    
    raise typer.Exit(0 if removed == len(stale_dirs) else 1)


@app.command("skills")
def doctor_skills(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    show_requirements: bool = typer.Option(False, "--requirements", help="Show detailed requirements"),
):
    """Check skills capabilities and requirements."""
    args = ["skills"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    if show_requirements:
        args.append("--requirements")
    raise typer.Exit(_run_doctor(args))


@app.command("runtime")
def doctor_runtime(
    team: str = typer.Option(None, "--team", help="Team YAML file to validate"),
    workflow: str = typer.Option(None, "--workflow", help="Workflow YAML file to validate (future)"),
    fix: bool = typer.Option(False, "--fix", help="Apply migration fixes automatically"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Show what would be fixed without applying changes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Config file to check (default: search for agents.yaml)"),
):
    """Check runtime configuration and migrate legacy cli_backend settings."""
    args = ["runtime"]
    if team:
        args.extend(["--team", team])
    if workflow:
        args.extend(["--workflow", workflow])
    if fix:
        args.append("--fix")
    if not dry_run:
        args.append("--execute")
    if json_output:
        args.append("--json")
    if deep:
        args.append("--deep")
    if file:
        args.extend(["--file", file])
    raise typer.Exit(_run_doctor(args))


@app.command("troubleshoot")
def doctor_troubleshoot():
    """
    Show troubleshooting information for common import errors.
    
    This command provides detailed troubleshooting steps for:
    - ImportError: cannot import name 'Agent' from 'praisonaiagents'
    - ModuleNotFoundError: No module named 'praisonaiagents'
    - Other common environment issues
    """
    output = get_output_controller()
    
    output.console.print("[bold cyan]PraisonAI Import Troubleshooting Guide[/bold cyan]\n")
    
    # Provide troubleshooting steps
    output.console.print("[bold]If you're seeing import errors:[/bold]\n")
    
    output.console.print("1. [yellow]Check for stale package artifacts:[/yellow]")
    output.console.print("   praisonai doctor cleanup --execute\n")
    
    output.console.print("2. [yellow]Reinstall praisonaiagents:[/yellow]")
    output.console.print("   pip uninstall praisonaiagents -y")
    output.console.print("   pip install praisonaiagents\n")
    
    output.console.print("3. [yellow]Check installation location:[/yellow]")
    output.console.print("   pip show praisonaiagents\n")
    
    output.console.print("4. [yellow]Verify Python path:[/yellow]")
    output.console.print("   python -c \"import sys; print('\\n'.join(sys.path))\"\n")
    
    output.console.print("5. [yellow]For editable installs, reinstall from source:[/yellow]")
    output.console.print("   git clone https://github.com/MervinPraison/PraisonAI.git")
    output.console.print("   cd PraisonAI/src/praisonai-agents")
    output.console.print("   pip install -e .\n")
    
    output.console.print("[dim]For more help, visit: https://github.com/MervinPraison/PraisonAI[/dim]")
    
    raise typer.Exit(0)