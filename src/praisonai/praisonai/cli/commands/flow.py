"""PraisonAI Flow — Visual workflow builder powered by Langflow.

Provides `praisonai flow` CLI command to launch Langflow with
PraisonAI custom components (Agent, Agents, Task) pre-loaded.
"""

import typer

app = typer.Typer(name="flow", help="Visual workflow builder (Langflow)")


@app.callback(invoke_without_command=True)
def flow_start(
    ctx: typer.Context,
    port: int = typer.Option(7860, "--port", "-p", help="Port to listen on"),
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Host to bind to"),
    env_file: str = typer.Option(None, "--env-file", help="Path to .env file"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser on start"),
    log_level: str = typer.Option(
        "error",
        "--log-level",
        "-l",
        help="Logging level (debug, info, warning, error, critical)",
    ),
    backend_only: bool = typer.Option(
        False, "--backend-only", help="Run backend API only (no frontend UI)"
    ),
    components_path: str = typer.Option(
        None,
        "--components-path",
        help="Additional custom components directory",
    ),
):
    """Start PraisonAI Flow — visual workflow builder.

    Launches Langflow with PraisonAI Agent, Agents, and Task components
    pre-loaded in the sidebar. Build complex AI workflows visually.

    Install: pip install praisonai[flow]

    Examples:
        praisonai flow
        praisonai flow --port 8080
        praisonai flow --host 0.0.0.0 --backend-only
    """
    if ctx.invoked_subcommand is not None:
        return

    import os
    import subprocess
    import sys
    from pathlib import Path

    from rich.console import Console

    console = Console()

    # Check langflow is installed
    try:
        import langflow  # noqa: F401
    except ImportError:
        console.print(
            "[red]Langflow is not installed.[/red]\n"
            "[yellow]Install with: pip install praisonai[flow][/yellow]"
        )
        raise typer.Abort()

    # Resolve PraisonAI components directory (absolute path)
    praison_components = str(
        (Path(__file__).parent.parent.parent / "flow" / "components").resolve()
    )

    # Set LANGFLOW_COMPONENTS_PATH env var (comma-separated for pydantic list parsing)
    env = os.environ.copy()
    existing = env.get("LANGFLOW_COMPONENTS_PATH", "")
    if components_path:
        all_paths = f"{praison_components},{components_path}"
    else:
        all_paths = praison_components
    env["LANGFLOW_COMPONENTS_PATH"] = (
        f"{all_paths},{existing}" if existing else all_paths
    )

    # Build langflow run command
    cmd = [
        sys.executable,
        "-m",
        "langflow",
        "run",
        "--port",
        str(port),
        "--host",
        host,
        "--log-level",
        log_level,
    ]
    if backend_only:
        cmd.append("--backend-only")
    if env_file:
        cmd.extend(["--env-file", env_file])
    if no_open:
        cmd.extend(["--open-browser", "false"])

    console.print()
    console.print("[bold green]🚀 Starting PraisonAI Flow[/bold green]")
    console.print(f"[dim]Langflow + PraisonAI components on {host}:{port}[/dim]")
    console.print(
        f"[dim]Components: {praison_components}[/dim]"
    )
    console.print()

    try:
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        console.print("\n[yellow]PraisonAI Flow stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error starting Langflow: {e}[/red]")
        raise typer.Abort()


@app.command("version")
def flow_version():
    """Show Langflow version information."""
    from rich.console import Console

    console = Console()

    try:
        from langflow.utils.version import get_version_info

        info = get_version_info()
        console.print(f"[bold]Langflow[/bold]: {info.get('version', 'unknown')}")
        console.print(f"[bold]Package[/bold]: {info.get('package', 'unknown')}")
    except ImportError:
        console.print(
            "[red]Langflow is not installed.[/red]\n"
            "[yellow]Install with: pip install praisonai[flow][/yellow]"
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
