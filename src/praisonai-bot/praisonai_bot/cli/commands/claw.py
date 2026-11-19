"""
Claw command — launch the PraisonAI 🦅 Dashboard.

``praisonai dashboard`` is the main name; ``praisonai claw`` opens the same app.

Usage:
    praisonai dashboard                # Dashboard on :8082 (or: praisonai claw)
    praisonai dashboard --port 9000    # Custom port
    praisonai dashboard --app my.py    # Custom app file
"""

import hashlib
import sys
from pathlib import Path
from typing import Optional

import typer

# No emoji in the Typer help: this string is what `praisonai --help`
# prints, and U+1F99E raises UnicodeEncodeError on a cp1252 console
# (Windows). #2699 removed emoji from praisonai-code's help strings for
# exactly this reason; the lazily-loaded bot command overrides the clean
# text registered in praisonai_code/cli/app.py, so it reintroduced one
# whenever praisonai-bot is installed. Runtime output below is
# unaffected -- only the help surface has to survive cp1252.
app = typer.Typer(help="PraisonAI Dashboard (same app as: praisonai dashboard)")

CLAW_DIR = Path.home() / ".praisonai" / "claw"
DEFAULT_APP = CLAW_DIR / "app.py"


# First line of every copy we write: the sha256 of the rest of the file, so an
# untouched copy can be told apart from one the user edited.
_STAMP = "# praisonai-default-app sha256="
# sha256[:16] of every default_app.py shipped before copies were stamped.
_SHIPPED = frozenset({
    "0f7d102b64e19354",
    "1bf3cf65bdea6869",
    "22a2836edefff014",
    "27b33fc7a2ca881c",
    "49f12c010797bdb3",
    "6359f55e85f43c20",
    "c7c2a42c5dce2aae",
    "eafe132c37a713fb",
    "efd0ea4dba9c050c",
})


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sync_default_app(bundled: Path, target: Path) -> str:
    """Create or refresh the user's copy of the bundled app; never overwrite an edited one.

    Returns "created", "updated", "current" or "edited".
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


def _ensure_default_app() -> Path:
    """Keep ~/.praisonai/claw/app.py on the bundled default unless the user edited it."""
    bundled = Path(__file__).parent.parent.parent / "claw" / "default_app.py"
    if not bundled.exists():
        if DEFAULT_APP.exists():
            return DEFAULT_APP
        print(f"ERROR: Bundled default_app.py not found at {bundled}")
        raise typer.Abort()

    state = _sync_default_app(bundled, DEFAULT_APP)
    if state == "created":
        print(f"   ✓ Created default dashboard config: {DEFAULT_APP}")
    elif state == "updated":
        print(f"   ✓ Updated {DEFAULT_APP} to the latest default")
    elif state == "edited":
        print(f"   Using your edited {DEFAULT_APP}. A newer default is at {bundled};"
              " delete your copy to get it.")
    return DEFAULT_APP


def _run_server(cmd) -> None:
    """Run the aiui server and stop it when this process is stopped.

    subprocess.run left the server running when this process got SIGTERM (a
    service manager, ``kill``, a closed terminal): the orphan kept the port and
    kept writing its in-memory state to config.yaml. SIGTERM now raises
    KeyboardInterrupt here, and the server is terminated (killed after 10 s).
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


@app.callback(invoke_without_command=True)
def claw(
    ctx: typer.Context,
    port: int = typer.Option(8082, "--port", "-p", help="Port to run dashboard on"),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help=(
            "Host to bind to (default: 127.0.0.1 — loopback only). "
            "Pass 0.0.0.0 to expose on the LAN; see docs for auth setup."
        ),
    ),
    app_file: Optional[str] = typer.Option(
        None, "--app", "-a", help="Custom app.py file (default: ~/.praisonai/claw/app.py)"
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """
    Launch the PraisonAI 🦅 Dashboard (same app as ``praisonai dashboard``).

    Starts the AIUI dashboard with chat, agents, memory, knowledge,
    channels, cron, guardrails, and more.

    Examples:
        praisonai dashboard          # or: praisonai claw
        praisonai dashboard --port 9000
        praisonai dashboard --app my-dashboard.py
    """
    if ctx.invoked_subcommand is not None:
        return

    # 1. Check praisonaiui is installed
    try:
        import importlib.util
        if importlib.util.find_spec("praisonaiui") is None:
            raise ImportError
    except ImportError:
        print("\n\033[91mERROR: PraisonAI Dashboard (aiui) is not installed.\033[0m")
        print('\nInstall with:\n  pip install "praisonai[dashboard]"\n')
        sys.exit(1)

    # 2. Resolve app file
    if app_file:
        resolved = Path(app_file)
        if not resolved.exists():
            print(f"\033[91mERROR: App file not found: {app_file}\033[0m")
            sys.exit(1)
    else:
        resolved = _ensure_default_app()

    # 3. Launch via aiui run, in this interpreter: a bare "aiui" from PATH can be a
    # different install (another venv or an old global copy) without praisonai_bot.
    cmd = [sys.executable, "-m", "praisonaiui.cli", "run", str(resolved),
           "--port", str(port), "--host", host]
    if reload:
        cmd.append("--reload")

    print(f"\n🦅 PraisonAI Dashboard starting at http://{host}:{port}")
    print(f"   App: {resolved}")
    # Warn if the user has opted into LAN exposure. The dashboard has no
    # built-in auth at the URL layer (see AuthConfig in praisonaiui), so
    # binding to a non-loopback address without extra guarding is risky.
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "\n\033[93m⚠  WARNING:\033[0m "
            f"Dashboard is bound to {host} — reachable from other hosts on your network.\n"
            "   The dashboard has no URL-level auth. For multi-user / remote use,\n"
            "   put it behind a reverse proxy or set praisonaiui AUTH_ENFORCE=true."
        )
    print("")

    try:
        _run_server(cmd)
    except KeyboardInterrupt:
        print("\n🦅 Dashboard stopped.")
