"""
Package command group for PraisonAI CLI.

Provides package management commands (pip-like).
"""

import typer

app = typer.Typer(help="Package management")


@app.command("install")
def package_install(
    package: str = typer.Argument(..., help="Package to install"),
    upgrade: bool = typer.Option(False, "--upgrade", "-U", help="Upgrade if already installed"),
):
    """Install a package."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['package', 'install', package]
    if upgrade:
        argv.append('--upgrade')
    
    run_wrapper_command(argv, feature="package")


@app.command("uninstall")
def package_uninstall(
    package: str = typer.Argument(..., help="Package to uninstall"),
):
    """Uninstall a package."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['package', 'uninstall', package]
    
    run_wrapper_command(argv, feature="package")


@app.command("list")
def package_list():
    """List installed packages."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['package', 'list']
    
    run_wrapper_command(argv, feature="package")
