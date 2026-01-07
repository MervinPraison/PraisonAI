"""
Code command group for PraisonAI CLI.

Provides terminal-native code assistant mode.
This command NEVER opens a browser - it runs entirely in the terminal.
"""

from typing import List, Optional

import typer

app = typer.Typer(help="Terminal-native code assistant mode")


@app.callback(invoke_without_command=True)
def code_main(
    ctx: typer.Context,
    prompt: Optional[str] = typer.Argument(None, help="Code task or question"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    tools: Optional[str] = typer.Option(None, "--tools", "-t", help="Tools file path"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    file: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Attach file(s) to context"),
    no_acp: bool = typer.Option(False, "--no-acp", help="Disable ACP tools (file operations)"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Disable LSP tools (code intelligence)"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
):
    """
    Start terminal-native code assistant mode.
    
    This is a terminal-based code assistant with file awareness, diff display,
    and ACP/LSP tools enabled by default. It NEVER opens a browser.
    
    For browser-based code UI, use: praisonai ui code
    
    Examples:
        praisonai code
        praisonai code "Refactor this function"
        praisonai code --model gpt-4o --workspace ./src
        praisonai code "Fix the bug" --file main.py
    """
    import os
    import argparse
    
    # Set workspace if provided
    if workspace:
        os.environ["PRAISONAI_WORKSPACE"] = workspace
    
    # Enable code-specific environment
    os.environ["PRAISONAI_CODE_MODE"] = "true"
    
    # Build args namespace for _start_interactive_mode
    args = argparse.Namespace()
    args.llm = model
    args.verbose = verbose
    args.tools = tools
    args.no_acp = no_acp
    args.no_lsp = no_lsp
    args.resume_session = session_id if session_id else ('last' if continue_session else None)
    
    # Import and run the terminal-native interactive mode
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    if prompt:
        # Single prompt mode - use _run_chat_mode with code context
        praison._run_chat_mode(prompt, args)
    else:
        # Interactive REPL mode - use _start_interactive_mode
        praison._start_interactive_mode(args)
