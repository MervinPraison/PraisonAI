"""
Agents command group for PraisonAI CLI.

Provides agent management commands.
"""

import typer

app = typer.Typer(help="Agent management")


@app.command("list")
def agents_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List available agents."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['agents', 'list']
    if verbose:
        argv.append('--verbose')
    
    run_wrapper_command(argv, feature="agents")


@app.command("create")
def agents_create(
    name: str = typer.Argument(..., help="Agent name"),
    template: str = typer.Option(None, "--template", "-t", help="Template to use"),
):
    """Create a new agent."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['agents', 'create', name]
    if template:
        argv.extend(['--template', template])
    
    run_wrapper_command(argv, feature="agents")


@app.command("info")
def agents_info(
    name: str = typer.Argument(..., help="Agent name"),
):
    """Show agent information."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['agents', 'info', name]
    
    run_wrapper_command(argv, feature="agents")
