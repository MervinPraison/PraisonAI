"""
Chat command group for PraisonAI CLI.

Provides terminal-native interactive chat mode.
This command NEVER opens a browser - it runs entirely in the terminal.
"""

from typing import List, Optional

import typer

app = typer.Typer(help="Terminal-native interactive chat mode")


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
    continue_session: bool = typer.Option(False, "--continue", "-c", help="Continue last session"),
    file: Optional[List[str]] = typer.Option(None, "--file", "-f", help="Attach file(s) to prompt"),
    workspace: Optional[str] = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    no_acp: bool = typer.Option(False, "--no-acp", help="Disable ACP tools"),
    no_lsp: bool = typer.Option(False, "--no-lsp", help="Disable LSP tools"),
    autonomy: bool = typer.Option(True, "--autonomy/--no-autonomy", help="Enable agent autonomy for complex tasks"),
    profile: bool = typer.Option(False, "--profile", help="Enable CLI profiling (timing breakdown)"),
    profile_deep: bool = typer.Option(False, "--profile-deep", help="Enable deep profiling (cProfile stats, higher overhead)"),
):
    """
    Start terminal-native interactive chat mode.
    
    This is a terminal REPL with streaming responses, slash commands,
    and multi-turn conversation support. It NEVER opens a browser.
    
    For browser-based chat UI, use: praisonai ui chat
    
    Examples:
        praisonai chat
        praisonai chat "Hello, how are you?"
        praisonai chat --model gpt-4o --memory
        praisonai chat --continue  # Resume last session
        praisonai chat "Summarize this" --file README.md
        praisonai chat "What is 2+2?" --profile
    """
    import asyncio
    import os
    
    # Set workspace if provided
    if workspace:
        os.environ["PRAISONAI_WORKSPACE"] = workspace
    
    # Handle profiling for single prompt mode
    if prompt and (profile or profile_deep):
        _run_profiled_chat(
            prompt=prompt,
            model=model,
            verbose=verbose,
            profile_deep=profile_deep,
        )
        return
    
    # Warn if profiling requested without prompt (REPL mode doesn't support profiling)
    if (profile or profile_deep) and not prompt:
        typer.echo("⚠️  Profiling is only supported for single prompt mode.", err=True)
        typer.echo("   Use: praisonai chat \"your prompt\" --profile", err=True)
    
    # Try InteractiveCore first (preferred terminal-native implementation)
    try:
        from praisonai.cli.interactive import InteractiveCore, InteractiveConfig
        from praisonai.cli.interactive.frontends import RichFrontend
        
        config = InteractiveConfig(
            model=model,
            session_id=session_id,
            continue_session=continue_session,
            workspace=workspace or None,
            verbose=verbose,
            memory=memory,
            files=list(file) if file else [],
            autonomy=autonomy,
        )
        
        core = InteractiveCore(config=config)
        
        if prompt:
            # Single prompt mode
            async def run_prompt():
                if continue_session:
                    core.continue_session()
                response = await core.prompt(prompt)
                print(response)
            
            asyncio.run(run_prompt())
        else:
            # Interactive REPL mode
            frontend = RichFrontend(core=core, config=config)
            asyncio.run(frontend.run())
            
    except ImportError:
        # Fallback to legacy terminal-native interactive mode
        _run_legacy_terminal_chat(
            prompt=prompt,
            model=model,
            verbose=verbose,
            memory=memory,
            tools=tools,
            user_id=user_id,
            session_id=session_id,
            continue_session=continue_session,
            workspace=workspace,
            no_acp=no_acp,
            no_lsp=no_lsp,
        )


def _run_profiled_chat(
    prompt: str,
    model: Optional[str] = None,
    verbose: bool = False,
    profile_deep: bool = False,
):
    """Run chat with profiling enabled."""
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
        "name": "ChatAgent",
        "role": "Assistant",
        "goal": "Help the user",
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


def _run_legacy_terminal_chat(
    prompt: Optional[str] = None,
    model: Optional[str] = None,
    verbose: bool = False,
    memory: bool = False,
    tools: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    continue_session: bool = False,
    workspace: Optional[str] = None,
    no_acp: bool = False,
    no_lsp: bool = False,
):
    """Run terminal-native chat using legacy _start_interactive_mode."""
    import argparse
    
    # Build args namespace for _start_interactive_mode
    args = argparse.Namespace()
    args.llm = model
    args.verbose = verbose
    args.memory = memory
    args.tools = tools
    args.user_id = user_id
    args.resume_session = session_id if session_id else ('last' if continue_session else None)
    args.no_acp = no_acp
    args.no_lsp = no_lsp
    
    # Import and run the terminal-native interactive mode
    from praisonai.cli.main import PraisonAI
    
    praison = PraisonAI()
    
    if prompt:
        # Single prompt mode - use _run_chat_mode
        praison._run_chat_mode(prompt, args)
    else:
        # Interactive REPL mode - use _start_interactive_mode
        praison._start_interactive_mode(args)
