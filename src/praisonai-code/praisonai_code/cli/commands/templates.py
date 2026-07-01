"""
Templates command group for PraisonAI CLI.

Provides template management commands.
"""

import typer

app = typer.Typer(help="Template management")


@app.command("list")
def templates_list():
    """List available templates."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['templates', 'list']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("create")
def templates_create(
    name: str = typer.Argument(..., help="Template name"),
    source: str = typer.Option(None, "--source", "-s", help="Source file to create template from"),
):
    """Create a new template."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['templates', 'create', name]
    if source:
        argv.extend(['--source', source])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
