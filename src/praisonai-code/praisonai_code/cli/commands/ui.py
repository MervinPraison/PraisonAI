"""
UI command — launch the PraisonAI Clean Chat UI.

Usage:
    praisonai ui                    # Chat on :8081
    praisonai ui --port 9000        # Custom port
    praisonai ui --app my-chat.py   # Custom app file
"""

import hashlib
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


# First line of every copy we write: the sha256 of the rest of the file, so an
# untouched copy can be told apart from one the user edited.
_STAMP = "# praisonai-default-app sha256="
# sha256[:16] of every ui_*/default_app.py shipped before copies were stamped.
_SHIPPED = frozenset({
    "10c4a61df56a5cbf",
    "1f7e4ab5e9d240c5",
    "45e4f37ecb08fe6a",
    "577b554be2d92c73",
    "5c2b778e207eafa7",
    "6808392fc180d31a",
    "8dcb4c9ab3c89d9c",
    "98baa6684c096592",
    "b9d53764ea495554",
    "c7fd2a667daf6a34",
    "d60e7b64c6969606",
    "de261b2f9f8aa43e",
    "e3e11ffd30b9eeb2",
    "f01947f507547615",
    "f9d7f5e8018c9140",
    "fa7b0c6151c81c7f",
})


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sync_default_app(bundled: Path, target: Path) -> str:
    """Create or refresh the user's copy of a bundled app; never overwrite an edited one.

    Returns "created", "updated", "current" or "edited". Same rules as
    praisonai_bot.cli.commands.claw (that package cannot import this one).
    """
    text = bundled.read_text(encoding="utf-8")
    stamped = f"{_STAMP}{_sha(text)}\n{text}"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(stamped, encoding="utf-8")
        return "created"
    old = target.read_text(encoding="utf-8")
    if old == stamped:
        return "current"
    first, _, body = old.partition("\n")
    untouched = (first == f"{_STAMP}{_sha(body)}") or _sha(old)[:16] in _SHIPPED
    if not untouched:
        return "edited"
    target.write_text(stamped, encoding="utf-8")
    return "updated"


def _run_server(cmd) -> None:
    """Run the aiui server and stop it when this process is stopped.

    subprocess.run left the server running when this process got SIGTERM (a
    service manager, ``kill``, a closed terminal). SIGTERM now raises
    KeyboardInterrupt here, and the server is terminated (killed after 10 s).
    Same rules as praisonai_bot.cli.commands.claw (that package cannot import
    this one).
    """
    import signal
    import subprocess

    def _on_sigterm(signum, frame):
        raise KeyboardInterrupt

    proc = subprocess.Popen(cmd)
    try:
        previous = signal.signal(signal.SIGTERM, _on_sigterm)
    except ValueError:  # not the main thread
        previous = None
    try:
        returncode = proc.wait()
    finally:
        if previous is not None:
            signal.signal(signal.SIGTERM, previous)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    if returncode:
        raise subprocess.CalledProcessError(returncode, cmd)


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
        default_app = Path.home() / ".praisonai" / app_dir / "app.py"
        # Bundled ui_*/default_app.py assets ship in the praisonai wrapper,
        # not in praisonai_code — resolve against the installed wrapper.
        bundled = _resolve_bundled_default_app(default_app_name)
        if bundled is None or not bundled.exists():
            if not default_app.exists():
                print(
                    "\033[91mERROR: Bundled default_app.py not found. "
                    'Install with:\n  pip install "praisonai[ui]"\033[0m'
                )
                sys.exit(1)
        else:
            state = _sync_default_app(bundled, default_app)
            if state == "created":
                print(f"   ✓ Created default {ui_name} config: {default_app}")
            elif state == "updated":
                print(f"   ✓ Updated {default_app} to the latest default")
            elif state == "edited":
                print(f"   Using your edited {default_app}. A newer default is at {bundled};"
                      " delete your copy to get it.")

        resolved = default_app

    # 3. Launch via aiui run, in this interpreter: a bare "aiui" from PATH can be a
    # different install (another venv or an old global copy).
    cmd = [sys.executable, "-m", "praisonaiui.cli", "run", str(resolved),
           "--port", str(port), "--host", host]
    if reload:
        cmd.append("--reload")

    print(f"\n🤖 PraisonAI {ui_name} starting at http://{host}:{port}")
    print(f"   App: {resolved}\n")

    try:
        _run_server(cmd)
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
