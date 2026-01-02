"""
Recipe command group for PraisonAI CLI.

Provides recipe management commands.
"""

import typer

app = typer.Typer(help="Recipe management")


@app.command("list")
def recipe_list():
    """List available recipes."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'list']
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("run")
def recipe_run(
    name: str = typer.Argument(..., help="Recipe name"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model to use"),
):
    """Run a recipe."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'run', name]
    if model:
        argv.extend(['--model', model])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("install")
def recipe_install(
    source: str = typer.Argument(..., help="Recipe source (path or URL)"),
):
    """Install a recipe."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'install', source]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
