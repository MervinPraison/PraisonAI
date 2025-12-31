"""
Version command group for PraisonAI CLI.

Provides version information:
- version show: Show version
- version check: Check for updates
"""

import typer

from ..output.console import get_output_controller

app = typer.Typer(help="Version information")


@app.command("show")
def version_show():
    """Show version information."""
    output = get_output_controller()
    
    from praisonai.version import __version__
    
    # Try to get additional version info
    versions = {
        "praisonai": __version__,
    }
    
    # Check praisonaiagents version
    try:
        import praisonaiagents
        versions["praisonaiagents"] = getattr(praisonaiagents, "__version__", "unknown")
    except ImportError:
        versions["praisonaiagents"] = "not installed"
    
    # Check Python version
    import sys
    versions["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    if output.is_json_mode:
        output.print_json(versions)
        return
    
    output.print_panel(
        f"PraisonAI: {versions['praisonai']}\n"
        f"PraisonAI Agents: {versions['praisonaiagents']}\n"
        f"Python: {versions['python']}",
        title="Version Information"
    )


@app.command("check")
def version_check():
    """Check for updates."""
    output = get_output_controller()
    
    from praisonai.version import __version__
    
    output.print_info("Checking for updates...")
    
    try:
        import urllib.request
        import json
        
        url = "https://pypi.org/pypi/praisonai/json"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            latest = data["info"]["version"]
        
        if output.is_json_mode:
            output.print_json({
                "current": __version__,
                "latest": latest,
                "update_available": latest != __version__,
            })
            return
        
        if latest != __version__:
            output.print_warning(
                f"Update available: {__version__} → {latest}\n"
                f"Run: pip install --upgrade praisonai"
            )
        else:
            output.print_success(f"You are using the latest version ({__version__})")
    
    except Exception as e:
        if output.is_json_mode:
            output.print_json({
                "current": __version__,
                "latest": None,
                "error": str(e),
            })
        else:
            output.print_error(f"Failed to check for updates: {e}")
            output.print(f"Current version: {__version__}")


@app.callback(invoke_without_command=True)
def version_callback(ctx: typer.Context):
    """Show version (default behavior)."""
    if ctx.invoked_subcommand is None:
        version_show()
