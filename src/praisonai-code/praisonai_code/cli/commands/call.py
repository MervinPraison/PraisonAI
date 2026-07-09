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
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['call']
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    
    run_wrapper_command(argv, feature="call")
