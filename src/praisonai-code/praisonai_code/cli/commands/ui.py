"""
UI command — launch the PraisonAI Clean Chat UI.

Usage:
    praisonai ui                    # Chat on :8081
    praisonai ui --port 9000        # Custom port
    praisonai ui --app my-chat.py   # Custom app file
"""

import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    help=(
        "PraisonAI Clean Chat UI (Pattern B host via bundled default_app). "
        "Pattern C: AIUIGateway. Legacy: PRAISONAI_HOST_LEGACY=1."
    )
)


def _resolve_bundled_default_app(default_app_name: str) -> Optional[Path]:
    """Locate a bundled ``ui_*/default_app.py`` inside the praisonai wrapper.

    The five bundled UI presets ship in the ``praisonai`` wrapper package
    (``praisonai/<name>/default_app.py``), not in ``praisonai_code`` where this
    loader now lives after the CLI extraction. Cross-tier wrapper access is
    routed through the lazy ``_wrapper_bridge`` per ARCHITECTURE.md §2 rather
    than traversing the wrapper package directly. Returns ``None`` when the
    wrapper is not installed so the caller can guide the user to
    ``pip install "praisonai[ui]"``.
    """
    from praisonai_code._wrapper_bridge import wrapper_package_path

    wrapper_path = wrapper_package_path()
    if wrapper_path is None:
        return None
    return wrapper_path / default_app_name / "default_app.py"


def _launch_aiui_app(
    app_dir: str,
    default_app_name: str,
    port: int,
    host: str,
    app_file: Optional[str],
    reload: bool,
    ui_name: str
) -> None:
    """Common function to launch aiui apps."""
    # 1. Check praisonaiui is installed
    try:
        import importlib.util
        if importlib.util.find_spec("praisonaiui") is None:
            raise ImportError
    except ImportError:
        print(f"\n\033[91mERROR: PraisonAI UI (aiui) is not installed.\033[0m")
        print('\nInstall with:\n  pip install "praisonai[ui]"\n')
        sys.exit(1)

    # 2. Resolve app file
    if app_file:
        resolved = Path(app_file)
        if not resolved.exists():
            print(f"\033[91mERROR: App file not found: {app_file}\033[0m")
            sys.exit(1)
    else:
        ui_dir = Path.home() / ".praisonai" / app_dir
        default_app = ui_dir / "app.py"
        
        # Ensure default app exists
        if not default_app.exists():
            ui_dir.mkdir(parents=True, exist_ok=True)
            # Bundled ui_*/default_app.py assets ship in the praisonai wrapper,
            # not in praisonai_code — resolve against the installed wrapper.
            bundled = _resolve_bundled_default_app(default_app_name)
            if bundled is None or not bundled.exists():
                print(
                    "\033[91mERROR: Bundled default_app.py not found. "
                    'Install with:\n  pip install "praisonai[ui]"\033[0m'
                )
                sys.exit(1)
            default_app.write_text(
            bundled.read_text(encoding="utf-8"), encoding="utf-8"
             )
            print(f"   ✓ Created default {ui_name} config: {default_app}")
        
        resolved = default_app

    # 3. Launch via aiui run
    import subprocess

    cmd = ["aiui", "run", str(resolved), "--port", str(port), "--host", host]
    if reload:
        cmd.append("--reload")

    print(f"\n🤖 PraisonAI {ui_name} starting at http://{host}:{port}")
    print(f"   App: {resolved}\n")

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        # Fallback: python -m praisonaiui.cli
        cmd = [sys.executable, "-m", "praisonaiui.cli", "run", str(resolved),
               "--port", str(port), "--host", host]
        if reload:
            cmd.append("--reload")
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print(f"\n🤖 {ui_name} stopped.")


@app.callback(invoke_without_command=True)
def ui(
    ctx: typer.Context,
    port: int = typer.Option(8081, "--port", "-p", help="Port to run chat UI on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    app_file: Optional[str] = typer.Option(
        None, "--app", "-a", help="Custom app.py file (default: ~/.praisonai/ui/app.py)"
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """
    Launch the PraisonAI Clean Chat UI.

    Starts a clean chat interface powered by PraisonAIUI — no sidebar,
    single-page chat experience.

    For the full dashboard with agents, memory, knowledge, etc.,
    use: praisonai claw

    Examples:
        praisonai ui
        praisonai ui --port 9000
        praisonai ui --app my-chat.py
        praisonai ui agents    # YAML agents dashboard
        praisonai ui bot       # Bot interface
        praisonai ui realtime  # Voice realtime
    """
    if ctx.invoked_subcommand is not None:
        return

    _launch_aiui_app("ui", "ui_chat", port, host, app_file, reload, "Chat")


@app.command()
def agents(
    port: int = typer.Option(8083, "--port", "-p", help="Port to run agents UI on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    app_file: Optional[str] = typer.Option(
        None, "--app", "-a", help="Custom app.py file"
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """
    Launch YAML Agents Dashboard.
    
    Replaces the old Chainlit agents interface with aiui.
    Loads agents from agents.yaml in the current directory.
    """
    _launch_aiui_app("ui_agents", "ui_agents", port, host, app_file, reload, "Agents Dashboard")


@app.command()
def bot(
    port: int = typer.Option(8084, "--port", "-p", help="Port to run bot UI on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    app_file: Optional[str] = typer.Option(
        None, "--app", "-a", help="Custom app.py file"
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """
    Launch Bot Interface.
    
    Replaces the old Chainlit bot interface with aiui.
    Provides step-by-step interaction visualization.
    """
    _launch_aiui_app("ui_bot", "ui_bot", port, host, app_file, reload, "Bot Interface")


@app.command()
def realtime(
    port: int = typer.Option(8085, "--port", "-p", help="Port to run realtime UI on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    app_file: Optional[str] = typer.Option(
        None, "--app", "-a", help="Custom app.py file"
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """
    Launch Realtime Voice Interface.
    
    Uses aiui's OpenAIRealtimeManager for WebRTC voice conversations.
    """
    _launch_aiui_app("ui_realtime", "ui_realtime", port, host, app_file, reload, "Realtime Voice")
