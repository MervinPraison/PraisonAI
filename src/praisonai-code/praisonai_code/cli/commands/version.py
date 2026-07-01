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
    
    from praisonai_code._version import get_package_version, get_wrapper_version

    code_version = get_package_version()
    wrapper_version = get_wrapper_version()

    versions = {
        "praisonai-code": code_version,
    }
    if wrapper_version:
        versions["praisonai"] = wrapper_version
    
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
        f"PraisonAI Code: {versions['praisonai-code']}\n"
        + (f"PraisonAI Wrapper: {versions['praisonai']}\n" if wrapper_version else "")
        + f"PraisonAI Agents: {versions['praisonaiagents']}\n"
        + f"Python: {versions['python']}",
        title="Version Information"
    )


@app.command("check")
def version_check():
    """Check for updates."""
    output = get_output_controller()
    
    from praisonai_code._version import get_package_version

    current = get_package_version()
    
    try:
        import urllib.request
        import json
        
        url = "https://pypi.org/pypi/praisonai-code/json"
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode())
            latest = data["info"]["version"]
        
        if output.is_json_mode:
            output.print_json({
                "current": current,
                "latest": latest,
                "update_available": latest != current,
            })
            return
        
        if latest != current:
            output.print_warning(
                f"Update available: {current} → {latest}\n"
                f"Run: pip install --upgrade praisonai-code"
            )
        else:
            output.print_success(f"You are using the latest version ({current})")
    
    except Exception as e:
        if output.is_json_mode:
            output.print_json({
                "current": current,
                "latest": None,
                "error": str(e),
            })
        else:
            output.print_error(f"Failed to check for updates: {e}")
            output.print(f"Current version: {current}")


@app.callback(invoke_without_command=True)
def version_callback(ctx: typer.Context):
    """Show version (default behavior)."""
    if ctx.invoked_subcommand is None:
        version_show()
