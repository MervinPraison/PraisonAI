"""
Code command group for PraisonAI CLI.

Provides code assistant commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Code assistant mode")


@app.callback(invoke_without_command=True)
def code_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Code task or question"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
):
    """
    Start code assistant mode.
    
    Examples:
        praisonai code
        praisonai code "Refactor this function"
        praisonai code --model gpt-4o --workspace ./src
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['code']
    if prompt:
        argv.append(prompt)
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    if tools:
        argv.extend(['--tools', tools])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
