"""
Doctor command group for PraisonAI CLI.

Wraps existing doctor functionality from features/doctor/.
Provides health checks and diagnostics.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Health checks and diagnostics")


def _run_doctor(args: list) -> int:
    """Run doctor command with args."""
    try:
        from ..features.doctor.handler import DoctorHandler
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
        output.print_error(f"Doctor error: {e}")
        return 1


@app.command("env")
def doctor_env(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    timeout: float = typer.Option(10.0, "--timeout", help="Per-check timeout"),
):
    """Check environment variables and API keys."""
    args = ["env"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    args.extend(["--timeout", str(timeout)])
    raise typer.Exit(_run_doctor(args))


@app.command("config")
def doctor_config(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check configuration files."""
    args = ["config"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("tools")
def doctor_tools(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check tools availability."""
    args = ["tools"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("db")
def doctor_db(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check database connections."""
    args = ["db"]
    if deep:
        args.append("--deep")
    if json_output:
        args.append("--json")
    raise typer.Exit(_run_doctor(args))


@app.command("mcp")
def doctor_mcp(
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Check MCP servers."""
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


@app.callback(invoke_without_command=True)
def doctor_callback(
    ctx: typer.Context,
    deep: bool = typer.Option(False, "--deep", help="Enable deeper probes"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
):
    """Run all fast health checks."""
    if ctx.invoked_subcommand is None:
        args = []
        if deep:
            args.append("--deep")
        if json_output:
            args.append("--json")
        if strict:
            args.append("--strict")
        if quiet:
            args.append("--quiet")
        raise typer.Exit(_run_doctor(args))
