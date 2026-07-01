"""
Research command group for PraisonAI CLI.

Provides research and analysis commands.
"""

import typer

app = typer.Typer(help="Research and analysis")


@app.callback(invoke_without_command=True)
def research_main(
    ctx: typer.Context,
    query: str = typer.Argument(None, help="Research query"),
    model: str = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """
    Run research and analysis tasks.
    
    Examples:
        praisonai research "What are the latest AI trends?"
        praisonai research --model gpt-4o "Analyze market data"
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['research']
    if query:
        argv.append(query)
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    if output:
        argv.extend(['--output', output])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
