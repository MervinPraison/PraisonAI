"""
Skills command group for PraisonAI CLI.

Provides skill management commands.
"""

import typer

app = typer.Typer(help="Skill management")


@app.command("list")
def skills_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List available skills."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'list']
    if verbose:
        argv.append('--verbose')
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("validate")
def skills_validate(
    path: str = typer.Argument(..., help="Skill directory path"),
):
    """Validate a skill."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'validate', path]
    
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
def skills_create(
    name: str = typer.Argument(..., help="Skill name"),
):
    """Create a new skill."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'create', name]
    
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
def skills_install(
    source: str = typer.Argument(..., help="Skill source (path or URL)"),
):
    """Install a skill."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'install', source]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
