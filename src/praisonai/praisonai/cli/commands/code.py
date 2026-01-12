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
    safe_mode: bool = typer.Option(False, "--safe", help="Safe mode: require approval for file writes and commands"),
    session_id: Optional[str] = typer.Option(None, "--session", "-s", help="Session ID to resume"),
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    autonomy: bool = typer.Option(True, "--autonomy/--no-autonomy", help="Enable agent autonomy for complex tasks"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
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
        praisonai code "What is 2+2?" --profile
    """
    import os
    import argparse
    
    # Set workspace if provided
    if workspace:
        os.environ["PRAISONAI_WORKSPACE"] = workspace
    
    # Enable code-specific environment
    os.environ["PRAISONAI_CODE_MODE"] = "true"
    
    # Set approval mode based on --safe flag
    if safe_mode:
        os.environ["PRAISON_APPROVAL_MODE"] = "prompt"
    else:
        os.environ["PRAISON_APPROVAL_MODE"] = "auto"
    
    # Handle profiling for single prompt mode
    if prompt and (profile or profile_deep):
        _run_profiled_code(
            prompt=prompt,
            model=model,
            verbose=verbose,
            profile_deep=profile_deep,
        )
        return
    
    # Warn if profiling requested without prompt (REPL mode doesn't support profiling)
    if (profile or profile_deep) and not prompt:
        typer.echo("⚠️  Profiling is only supported for single prompt mode.", err=True)
        typer.echo("   Use: praisonai code \"your prompt\" --profile", err=True)
    
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


def _run_profiled_code(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
):
    """Run code assistant with profiling enabled."""
    from praisonai.cli.features.cli_profiler import (
        CLIProfileConfig,
        CLIProfiler,
    )
    
    config = CLIProfileConfig(enabled=True, deep=profile_deep)
    profiler = CLIProfiler(config)
    
    if profile_deep:
        typer.echo("⚠️  Deep profiling enabled - this adds significant overhead", err=True)
    
    profiler.start()
    
    # Import phase
    profiler.mark_import_start()
    try:
        from praisonaiagents import Agent
    except ImportError:
        typer.echo("Error: praisonaiagents not installed", err=True)
        raise typer.Exit(1)
    profiler.mark_import_end()
    
    # Agent initialization phase
    profiler.mark_init_start()
    agent_config = {
        "name": "CodeAgent",
        "role": "Code Assistant",
        "goal": "Help with coding tasks",
        "verbose": verbose,
    }
    if model:
        agent_config["llm"] = model
    
    agent = Agent(**agent_config)
    profiler.mark_init_end()
    
    # Execution phase
    profiler.mark_exec_start()
    response = agent.start(prompt)
    profiler.mark_exec_end()
    
    profiler.stop()
    
    # Print response
    if response:
        print(response)
    
    # Print profiling report
    profiler.print_report()
