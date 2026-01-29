"""
UI command group for PraisonAI CLI.

Provides all browser-based UI commands.
ALL browser UIs are under this namespace - nothing outside 'praisonai ui' opens a browser.
"""

import typer

app = typer.Typer(help="Browser-based web UI (all browser modes)")


@app.callback(invoke_without_command=True)
def ui_main(
    ctx: typer.Context,
    port: int = typer.Option(8082, "--port", "-p", help="Port to run UI on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    public: bool = typer.Option(False, "--public", help="Make UI publicly accessible"),
):
    """
    Start the default web UI (agents management).
    
    DEPRECATED: Use `praisonai serve ui` instead.
    
    All browser-based UIs are under this namespace:
    - praisonai ui         - Default agents UI
    - praisonai ui chat    - Chat interface
    - praisonai ui code    - Code assistant interface
    - praisonai ui realtime - Voice/realtime interface
    - praisonai ui gradio  - Gradio interface
    
    Examples:
        praisonai ui
        praisonai ui --port 3000
        praisonai ui --public
    """
    import sys
    
    # Print deprecation warning
    print("\n\033[93m⚠ DEPRECATION WARNING:\033[0m", file=sys.stderr)
    print("\033[93m'praisonai ui' is deprecated and will be removed in a future version.\033[0m", file=sys.stderr)
    print("\033[93mPlease use 'praisonai serve ui' instead.\033[0m\n", file=sys.stderr)
    
    # If a subcommand was invoked, don't run the default
    if ctx.invoked_subcommand is not None:
        return
    
    # Default: launch agents UI (Chainlit)
    _launch_chainlit_ui("agents", port, host, public)


@app.command("chat")
def ui_chat(
    port: int = typer.Option(8084, "--port", "-p", help="Port to run UI on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    public: bool = typer.Option(False, "--public", help="Make UI publicly accessible"),
):
    """
    Start the browser-based chat UI (Chainlit).
    
    For terminal-native chat, use: praisonai chat
    
    Examples:
        praisonai ui chat
        praisonai ui chat --port 3000
    """
    _launch_chainlit_ui("chat", port, host, public)


@app.command("code")
def ui_code(
    port: int = typer.Option(8086, "--port", "-p", help="Port to run UI on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    public: bool = typer.Option(False, "--public", help="Make UI publicly accessible"),
):
    """
    Start the browser-based code assistant UI (Chainlit).
    
    For terminal-native code assistant, use: praisonai code
    
    Examples:
        praisonai ui code
        praisonai ui code --port 3000
    """
    _launch_chainlit_ui("code", port, host, public)


@app.command("realtime")
def ui_realtime(
    port: int = typer.Option(8088, "--port", "-p", help="Port to run UI on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    public: bool = typer.Option(False, "--public", help="Make UI publicly accessible"),
):
    """
    Start the browser-based realtime/voice UI (Chainlit).
    
    Examples:
        praisonai ui realtime
        praisonai ui realtime --port 3000
    """
    _launch_chainlit_ui("realtime", port, host, public)


@app.command("gradio")
def ui_gradio(
    port: int = typer.Option(8080, "--port", "-p", help="Port to run UI on"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    public: bool = typer.Option(False, "--public", help="Make UI publicly accessible"),
):
    """
    Start the Gradio-based web UI.
    
    Examples:
        praisonai ui gradio
        praisonai ui gradio --port 3000
    """
    _launch_gradio_ui(port, host, public)


def _launch_chainlit_ui(ui_type: str, port: int, host: str, public: bool):
    """Launch a Chainlit-based UI."""
    import os
    import sys
    
    try:
        import importlib.util
        CHAINLIT_AVAILABLE = importlib.util.find_spec("chainlit") is not None
    except ImportError:
        CHAINLIT_AVAILABLE = False
    
    if not CHAINLIT_AVAILABLE:
        install_extra = {
            "agents": "ui",
            "chat": "chat",
            "code": "code",
            "realtime": "realtime",
        }.get(ui_type, "ui")
        print(f"[red]ERROR: {ui_type.title()} UI is not installed. Install with:[/red]")
        print(f'\npip install "praisonai[{install_extra}]"\n')
        sys.exit(1)
    
    import praisonai
    
    # Set environment variables
    os.environ["CHAINLIT_PORT"] = str(port)
    os.environ["CHAINLIT_HOST"] = host
    
    root_path = os.path.join(os.path.expanduser("~"), ".praison")
    if "CHAINLIT_APP_ROOT" not in os.environ:
        os.environ["CHAINLIT_APP_ROOT"] = root_path
    
    # Determine UI script path
    ui_scripts = {
        "agents": "chainlit_ui.py",
        "chat": os.path.join("ui", "chat.py"),
        "code": os.path.join("ui", "code.py"),
        "realtime": os.path.join("ui", "realtime.py"),
    }
    
    ui_script = ui_scripts.get(ui_type, "chainlit_ui.py")
    ui_path = os.path.join(os.path.dirname(praisonai.__file__), ui_script)
    
    print(f"Starting {ui_type} UI at http://{host}:{port}")
    
    # Use subprocess to run chainlit with proper CLI args
    import subprocess
    
    cmd = ["chainlit", "run", ui_path, "--host", host, "--port", str(port)]
    if public:
        cmd.append("--public")
    
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        # Fallback: try running with python -m chainlit
        cmd = [sys.executable, "-m", "chainlit", "run", ui_path, "--host", host, "--port", str(port)]
        if public:
            cmd.append("--public")
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nUI stopped.")


def _launch_gradio_ui(port: int, host: str, public: bool):
    """Launch the Gradio-based UI."""
    import sys
    import importlib.util
    
    GRADIO_AVAILABLE = importlib.util.find_spec("gradio") is not None
    
    if not GRADIO_AVAILABLE:
        print("[red]ERROR: Gradio UI is not installed. Install with:[/red]")
        print('\npip install "praisonai[gradio]"\n')
        sys.exit(1)
    
    from praisonai.cli.main import PraisonAI
    praison = PraisonAI()
    praison.create_gradio_interface()
