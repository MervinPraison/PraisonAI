"""
Call command group for PraisonAI CLI.

Provides voice/call interaction commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Voice/call interaction mode")


@app.callback(invoke_without_command=True)
def call_main(
    ctx: typer.Context,
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """
    Start voice/call interaction mode.
    
    Examples:
        praisonai call
        praisonai call --model gpt-4o
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['call']
    if model:
        argv.extend(['--model', model])
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
