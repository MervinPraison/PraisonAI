"""
Chat command group for PraisonAI CLI.

Provides interactive chat commands.
"""

from typing import Optional

import typer

app = typer.Typer(help="Interactive chat mode")


@app.callback(invoke_without_command=True)
def chat_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Initial prompt for chat"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    memory: bool = typer.Option(False, "--memory", help="Enable memory"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    user_id: Optional[str] = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
):
    """
    Start interactive chat mode.
    
    Examples:
        praisonai chat
        praisonai chat "Hello, how are you?"
        praisonai chat --model gpt-4o --memory
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    # Build args for legacy handler
    argv = ['chat']
    if prompt:
        argv.append(prompt)
    if model:
        argv.extend(['--model', model])
    if verbose:
        argv.append('--verbose')
    if memory:
        argv.append('--memory')
    if tools:
        argv.extend(['--tools', tools])
    if user_id:
        argv.extend(['--user-id', user_id])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
