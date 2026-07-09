"""
Templates command group for PraisonAI CLI.

Provides template management commands.
"""

import typer

app = typer.Typer(help="Template management")


@app.command("list")
def templates_list():
    """List available templates."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['templates', 'list']
    
    run_wrapper_command(argv, feature="templates")


@app.command("create")
def templates_create(
    name: str = typer.Argument(..., help="Template name"),
    source: str = typer.Option(None, "--source", "-s", help="Source file to create template from"),
):
    """Create a new template."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['templates', 'create', name]
    if source:
        argv.extend(['--source', source])
    
    run_wrapper_command(argv, feature="templates")
