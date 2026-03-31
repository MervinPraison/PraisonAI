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

app = typer.Typer(help="🤖 PraisonAI Clean Chat UI")

UI_DIR = Path.home() / ".praisonai" / "ui"
DEFAULT_APP = UI_DIR / "app.py"


def _ensure_default_app() -> Path:
    """Copy bundled default_app.py to ~/.praisonai/ui/app.py if missing."""
    if DEFAULT_APP.exists():
        return DEFAULT_APP

    UI_DIR.mkdir(parents=True, exist_ok=True)

    # Read the bundled default
    bundled = Path(__file__).parent.parent.parent / "ui_chat" / "default_app.py"
    if not bundled.exists():
        print(f"\033[91mERROR: Bundled default_app.py not found at {bundled}\033[0m")
        raise typer.Abort()

    DEFAULT_APP.write_text(bundled.read_text())
    print(f"   ✓ Created default chat config: {DEFAULT_APP}")
    return DEFAULT_APP


@app.callback(invoke_without_command=True)
def ui(
    ctx: typer.Context,
    port: int = typer.Option(8081, "--port", "-p", help="Port to run chat UI on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
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
    """
    if ctx.invoked_subcommand is not None:
        return

    # 1. Check praisonaiui is installed
    try:
        import importlib.util
        if importlib.util.find_spec("praisonaiui") is None:
            raise ImportError
    except ImportError:
        print("\n\033[91mERROR: PraisonAI UI (aiui) is not installed.\033[0m")
        print('\nInstall with:\n  pip install "praisonai[ui]"\n')
        sys.exit(1)

    # 2. Resolve app file
    if app_file:
        resolved = Path(app_file)
        if not resolved.exists():
            print(f"\033[91mERROR: App file not found: {app_file}\033[0m")
            sys.exit(1)
    else:
        resolved = _ensure_default_app()

    # 3. Launch via aiui run
    import subprocess

    cmd = ["aiui", "run", str(resolved), "--port", str(port), "--host", host]
    if reload:
        cmd.append("--reload")

    print(f"\n🤖 PraisonAI Chat starting at http://{host}:{port}")
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
        print("\n🤖 Chat stopped.")
