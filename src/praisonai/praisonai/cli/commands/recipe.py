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
    var: list[str] = typer.Option(None, "--var", help="Variable override (key=value), can be used multiple times"),
    save: bool = typer.Option(False, "--save", "-s", help="Save replay trace for debugging"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    output: str = typer.Option(None, "--output", "-o", help="Output mode: silent, status, trace, verbose, debug"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug mode"),
    profile: bool = typer.Option(False, "--profile", help="Enable profiling"),
    deep_profile: bool = typer.Option(False, "--deep-profile", help="Enable deep profiling"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without executing"),
    force: bool = typer.Option(False, "--force", help="Force execution even with missing deps"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
):
    """Run a recipe with optional variable overrides.
    
    Examples:
        praisonai recipe run ai-url-blog-generator --var url="https://example.com/article"
        praisonai recipe run ai-dynamic-blog-generator --var topic="LangGraph 0.3" --var style="coding"
        praisonai recipe run ai-wordpress-post-generator --save --verbose
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['recipe', 'run', name]
    if model:
        argv.extend(['--model', model])
    
    # Pass --var directly to the recipe handler (features/recipe.py)
    # Don't convert to --workflow-var as that gets consumed by main.py's parser
    if var:
        for v in var:
            argv.extend(['--var', v])
    
    # Forward all flags to the recipe handler
    if save:
        argv.append('--save')
    if verbose:
        argv.append('--verbose')
    if output:
        argv.extend(['--output', output])
    if debug:
        argv.append('--debug')
    if profile:
        argv.append('--profile')
    if deep_profile:
        argv.append('--deep-profile')
    if dry_run:
        argv.append('--dry-run')
    if force:
        argv.append('--force')
    if json_output:
        argv.append('--json')
    
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
