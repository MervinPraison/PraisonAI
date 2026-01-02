"""
Knowledge command group for PraisonAI CLI.

Provides knowledge base management commands.
"""

import typer

app = typer.Typer(help="Knowledge base management")


@app.command("add")
def knowledge_add(
    source: str = typer.Argument(..., help="Source file or URL"),
    name: str = typer.Option(None, "--name", "-n", help="Knowledge base name"),
):
    """Add knowledge from a source."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['knowledge', 'add', source]
    if name:
        argv.extend(['--name', name])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("list")
def knowledge_list():
    """List knowledge bases."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['knowledge', 'list']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("search")
def knowledge_search(
    query: str = typer.Argument(..., help="Search query"),
):
    """Search knowledge base."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['knowledge', 'search', query]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
